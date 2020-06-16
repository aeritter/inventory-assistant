# Need to create flowchart and datastore tree


# incoming document > pass through document split function > each page group used to create document object > doc object added to inventory object, inventory object initialized for loading info from doc text > inv object sent to Database for reconciliation, return "New" or "Merged"
#                   - if numPages in result = numPages in doc, rename and move rather than move to unsplit and create new doc
# database class only accepts Inventory objects as input
# database class can return contents formatted for output

version = '1.0.0'

import re, os.path, subprocess, time, importlib, sys
import win32file, win32con, win32event, win32net, pywintypes
import json, requests, multiprocessing, threading, configparser
import fitz # fitz = PyMuPDF
from PyPDF2 import PdfFileReader as PDFReader 
from PyPDF2 import PdfFileWriter as PDFWriter
from PyPDF2 import pdf as pdfObj
from pathlib import Path


mainFolder = os.path.dirname(os.path.abspath(__file__))+"/"
config = configparser.ConfigParser()
config.read(mainFolder+'settings.ini')


pdfFolderLocation = config['Paths']['pdf_folder']+"/"
if pdfFolderLocation[:2] == '//' or pdfFolderLocation[:2] == '\\\\':
    netdata = {
        'remote': config['Paths']['pdf_folder'],
        'local':'',
        'username':config['NetCredentials']['username'],
        'domainname':config['NetCredentials']['domain_name'],
        'password':config['NetCredentials']['password']
    }
    win32net.NetUseAdd(None, 2, netdata)

DebugFolder = config['Paths']['debug_folder']
DoneFolder = config['Paths']['done_folder']
ErroredFolder = config['Paths']['errored_folder']
SettingsFolder = config['Paths']['settings_folder']
SuspendedFolder = config['Paths']['suspended_folder']
OriginalDocsFolder = config['Paths']['original_docs_folder']
DocumentsFolder = config['Paths']['documents_folder']
pdftotextExecutable = SettingsFolder+"/pdftotext.exe"

airtableURL = config['Other']['airtable_url']
slackURL = config['Other']['slack_url']
airtableURLFields = config['Other']['airtable_url_fields']
airtableAPIKey = config['Other']['airtable_api_key']
readDirTimeout = int(config['Other']['read_dir_timeout'])*1000     # *1000 to convert milliseconds to seconds
debug = config['Other'].getboolean('enable_debug')
enableAirtablePosts = config['Other'].getboolean('enable_airtable_posts')
enableSlackPosts = config['Other'].getboolean('enable_slack_posts')
enableSlackStatusUpdate = config['Other'].getboolean('enable_status_update')
CheckinHour = int(float(config['Other']['check-in_hour'])*60*60)
TimeBetweenCheckins = float(config['Other']['time_between_check-ins_in_minutes'])*60*10000000 #converted to 100 nanoseconds for the function


reSearchInvoiceNum = re.compile(r'(?<= )\d{7}(?= |\n)|\d{2}/\d{5}')

class page(object):
    def __init__(self, text):
        self.text = text
        try:
            search = reSearchInvoiceNum.search(self.text)
            if search != None:
                self.invoiceNumber = search.group(0)
            elif search == None:
                print(self.text)
            else:
                raise Exception
        except:
            print("Couldn't find invoice num")
            print("First 3 lines:")
            print(self.text.split('\n', 3))
    def getPageType(self):                                      #NOTE: needs refining, separate out into changable variables: lines = list(self.text.readlines()), for x in variables: if x["lineContent"] in lines[x["lineNumber"]-1]: return x["Type"]
        if self.text.count('\n') > 5:
            line1 = self.text.split('\n', 1)[0]                 # first line of .txt file
            line2 = self.text.split('\n', 2)[1]                 # second line of .txt file
            line5 = self.text.split('\n', 5)[4]                 # 5th line
            if "Welcome to Volvo" in line1:
                return "Volvo Order"
            elif "GSO:" in line2:
                return "Mack Order"
            elif "CREDIT MEMO" in line2:
                return "Credit Memo"
            elif "SUPPLEMENT" in line5:
                return "Supplement"
            elif "MACK TRUCKS, INC." in line1:
                return "Mack Invoice"
            elif "PAGE 1" in line1 or "PAGE  1" in line1 or "PAGE   1" in line1:
                return "Volvo Invoice"
        # use regex to determine page type, make sure it only matches the first page in a group

class document(object):
    def __init__(self, pageClass):
        if type(pageClass) == list:
            self.pages = pageClass
        else:
            self.pages = [pageClass]
        ## The following are set by the PDFSplitter function
        self.invoiceNumber = None           # unique document identifier
        self.orderNumber = None             # truck identifier (multiple docs have this)
        # self.VIN = None
        self.docType = None
        self.location = None

    
    def getText(self):
        return "".join(x.text for x in self.pages)

    def addPage(self, pageClass):
        self.pages.append(pageClass)

    def getSpecs(self):
        # return {'Engine':'D18'}
        return {1:self.getText}

    

class inventoryObject(object): 
    def __init__(self, uniqueIdentifier):
        self.uniqueIdentifier = uniqueIdentifier
        self.documents = []             # refers to document class
        self.specs = None               # dictionary of specs eg. {"Engine Model":"D13"}
        self.airtableRefID = None
    def formatForAirtableUpdate(self):
        return {"id":self.airtableRefID, "fields":self.specs}
    def formatForAirtableCreate(self):
        return {"fields":self.specs}
    def getSpecsFromDocs(self):
        if len(self.documents) == 0:
            raise Exception("self.documents does not contain any information")
        for x in self.documents:
            self.specs.update(x.getSpecs())
        
        

class datastore(object):
    def __init__(self, pool):
        self.inventory = {}             # dictionary of inventory UIDs and the corresponding inventory object eg. {"12345":inventoryObject()}
        self.MultiprocessingPool = pool
        # for x in retrieveRecordsFromAirtable():
        #     stockNo = x['fields']['Stock No.']
        #     t = inventoryObject(stockNo)
        #     t.airtableRefID = x['id']
        #     self.inventory[stockNo] = t
    def addToInventory(self, newInvObj):
        if newInvObj.uniqueIdentifier in self.inventory:
            print("Inventory object exists: "+str(newInvObj.uniqueIdentifier))
            oldInvObj = self.inventory[newInvObj.uniqueIdentifier]

            # add documents from incoming inventory object to existing inventory object if they do not currently exist there
            if newInvObj.documents != None:
                for x in newInvObj.documents:
                    # Compare between the new documents and the old documents, using a list of the contents of each page object's dictionary.
                    if not any([z.__dict__ for z in x.__dict__['pages']] == [c.__dict__ for c in y.__dict__['pages']] for y in oldInvObj.documents):
                        print("New doc added to inventory object: "+oldInvObj.uniqueIdentifier)
                        oldInvObj.documents.append(x)
            
            # add incoming specs to existing inventory object
            if newInvObj.specs != None:
                oldInvObj.specs.update(newInvObj.specs)

        else:
            self.inventory[newInvObj.uniqueIdentifier] = newInvObj
            # print("Created Inventory object: "+str(newInvObj.uniqueIdentifier))
                
    
    

class PDFProcessingSettingsObj(object):
    def __init__(self): 
        self.update()
    def update(self):
        try:
            time.sleep(.1)
            with open(SettingsFolder+"pdfProcessingSettings.json", 'r') as clist:
                self.data = json.load(clist)
            self.determineFileType = self.data["determineFileType"]

        except Exception as exc:        
            appendToDebugLog("Could not update from pdfProcessingSettings.json", **{"Error":exc})
            return False              # if conversionlists.py could not be loaded, move files to Errored and update the Debug log with the error
        else:                       # if no errors in reloading conversionlists.py, update cache and run!
            return True

def getPDFText(filePath, pageToConvert=0):  # pageToConvert=0 means all pages.
    try:
        fileText = subprocess.run([pdftotextExecutable, '-f', str(pageToConvert), '-l', str(pageToConvert), '-simple', '-raw', filePath,'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
    except Exception as exc:
        print("getPDFText() failed: ",str(exc))
        return "Error"
    return fileText

def getPDFsInFolder(folderLocation):
    filesInFolder = []
    for filename in os.listdir(folderLocation):
        if str(filename)[-3:] == 'pdf':
            filesInFolder.append([folderLocation, filename])
    return filesInFolder


def appendToDebugLog(errormsg,**kwargs):
    errordata = str(errormsg + "\n"+'\n'.join('{0}: {1!r}'.format(x, y) for x, y in kwargs.items())+'\n')
    print(errordata)
    try:
        a = open(DebugFolder+"Debug log.txt", "a+")
        a.write("\n"+str(time.ctime())+' '+errordata)
        a.close()
    except:
        print("Can't append to debug log file.")
    try:
        if enableSlackPosts == True:
            requests.post(slackURL,json={'text':errordata},headers={'Content-type':'application/json'})
    except:
        print("Could not post to Slack!")


def retrieveRecordsFromAirtable(offset=None):
    while True:
        try:
            # if enableAirtablePosts != True:
            #     return "Airtable connection disabled."
            if offset == None:
                x = requests.get(airtableURL+airtableURLFields, data=None, headers=AirtableAPIHeaders)
            else:
                x = requests.get(airtableURL+airtableURLFields+"&offset="+offset, data=None, headers=AirtableAPIHeaders)

            records = x.json()['records']
            if 'offset' in json.loads(x.text):
                records.extend(retrieveRecordsFromAirtable(json.loads(x.text)['offset']))
            return records
                
        except ConnectionError:
            print("Could not connect to airtable.com")
            time.sleep(30)

def PDFSplitter(pdfLocation, pdfFilename, splitLocation=DocumentsFolder):
    pageGroups = {None:[]}  # Pages with no uniqueIdentifier will go to the None entry, where they will be added to an ErroredPages.pdf file and appended to the debug log
    while True:
        try:
            with open(pdfLocation+pdfFilename, 'rb') as do:
                docstream = do.read()
                break
        except:
            print("Attempted to access file too early. Waiting one second.")
            time.sleep(1)
    doc = fitz.open(stream=docstream, filetype="pdf")

    # Create a list of page objects for each page found
    pdfPageList = [page(x) for x in getPDFText(pdfLocation+pdfFilename).split('\f')[:-1]]  #last entry will always be empty, as the document will always end with a \f value
    print("Done making page objects from pdftotext.exe")
    ctime = time.time()

    # Error out if the number of pages found between PyMuPDF and pdftotext.exe do not match.
    if doc.pageCount != len(pdfPageList):
        appendToDebugLog("Number of page objects does not equal number of pages found after text conversion", **{"Document":pdfLocation+pdfFilename})
        return Exception

    # if self.inDebugFolder == True:
    #     return

    # Create page groups from page invoice numbers
    docs = {None:[]}
    for pdfPageNum, pdfPage in enumerate(pdfPageList):
        if pdfPage.invoiceNumber in pageGroups:
            pageGroups[pdfPage.invoiceNumber].addPage(pdfPage)
            docs[pdfPage.invoiceNumber].insertPDF(doc, from_page=pdfPageNum, to_page=pdfPageNum)
        else:
            y = document(pdfPage)
            y.invoiceNumber = pdfPage.invoiceNumber
            y.docType = pdfPage.getPageType()
            y.location = str(splitLocation+y.docType+" - "+y.invoiceNumber.replace('/','')+".pdf")
            pageGroups[pdfPage.invoiceNumber] = y

            z = fitz.open()
            z.insertPDF(doc, from_page=pdfPageNum, to_page=pdfPageNum)
            docs[pdfPage.invoiceNumber] = z

            
    print("Now writing invoices.")
    # Write problem pages to the Errored Pages pdf.
    if len(pageGroups[None]) > 0:
        print("Errored pages!")
        ErroredPagesPDF = fitz.open(DebugFolder+"Errored Pages.pdf")
        ErroredPagesPDF.insertPDF(docs[None])
        ErroredPagesPDF.saveIncr()

    # Remove entry for problem pages
    pageGroups.pop(None)
    docs.pop(None)

    # Write PDFs from page groups.
    writethreads = [threading.Thread(target=(writePDFfromSplitter), args=([docs[z], pageGroups[z].location])) for z in docs]
    for thread in writethreads:
        thread.start()
    for thread in writethreads:
        thread.join()

    # Send document objects back to main() so inventory objects can be created and sent to the database.
    print("Time taken to split PDF after pdftotext.exe: "+str(time.time()-ctime))
    doc.close()
    return pageGroups

def writePDFfromSplitter(doc, location):
    # print("Writing doc: "+location)
    while True:
        try:
            doc.save(location)
            doc.close()
            break
        except:
            time.sleep(1)
            print("Error saving: "+location)


def moveToFolder(oldFolder, oldName, newFolder, newName=None):
    if newName == None:
        newName = oldName
    try:
        os.rename(oldFolder+oldName, newFolder+newName)
    except FileExistsError:
        print("File", newName, "exists in", newFolder, "folder.")
        try:
            os.rename(oldFolder+oldName, newFolder+"Already Exists\\"+newName[:-4]+" (1)"+newName[-4:])  
        except:
            os.remove(oldFolder+oldName)
            pass
        pass
    except FileNotFoundError:
        print(oldName+" not found.")
        pass


def startProcessing(x):
    return PDFSplitter(x[0], x[1])

def main(pool):
    try:
        # if initialize.Folder_Check() != True:
        #     print("Folder check failed")
        #     raise Exception("Folder check failed")
        
        db = datastore(pool)

        pdfProcessingData.update()
        flags = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
        directoryHandle = win32file.CreateFile(pdfFolderLocation, 0x0001,win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
        startTime = time.localtime()
        timerHandle = win32event.CreateWaitableTimer(None, True, None)
        # win32event.SetWaitableTimer(timerHandle, int(0-initialCheckinTimeConverted), 0, None, None, True)
        overlapped = pywintypes.OVERLAPPED()
        overlapped.hEvent = win32event.CreateEvent(None, 0, 0, None)
        buffer = win32file.AllocateReadBuffer(8192)

        print("Waiting for files.")

        # lastCheckTime = 0
        # conversionlistsOK = True
        hasTimedOut = False
        while True:
            if hasTimedOut == False:
                win32file.ReadDirectoryChangesW(directoryHandle, buffer, True, flags, overlapped)

            rc = win32event.MsgWaitForMultipleObjects([overlapped.hEvent, timerHandle], False, readDirTimeout, win32event.QS_ALLEVENTS)
            if rc == win32event.WAIT_TIMEOUT:
                hasTimedOut = True      # apparently simply reassigning is faster than checking value and assigning if it did not match
                print(time.ctime(),' Wait timeout.')
                pool.imap_unordered(startProcessing, getPDFsInFolder(pdfFolderLocation))
            elif rc == win32event.WAIT_OBJECT_0:
                hasTimedOut = False
                result = win32file.GetOverlappedResult(directoryHandle, overlapped, True)
                if result:
                    bufferData = win32file.FILE_NOTIFY_INFORMATION(buffer, result)
                    for x, filename in bufferData:
                        print('Change found: '+filename)

                        fileloc = pdfFolderLocation+filename[:-len(filename.split("\\")[-1])]
                        if x == 1 and filename[-3:] == 'pdf' and '\\' not in filename:
                            docs = list(item for item in pool.imap_unordered(startProcessing, [[fileloc, filename]]))[0].values()
                            
                            for v, y in enumerate(docs):
                                specs = y.getSpecs()
                                # z = inventoryObject(specs["Order Number"])
                                z = inventoryObject(str(v))
                                z.documents.append(y)
                                z.specs = specs
                                db.addToInventory(z)

                            # Move original PDF away
                            moveToFolder(fileloc, filename, OriginalDocsFolder)


                        # if 'pdfProcessingSettings.json' in filename:
                        #     if time.time() - lastCheckTime < .5:
                        #         break
                        #     lastCheckTime = time.time()
                        #     conversionlistsCheck = pdfProcessingData.update()
                        #     if conversionlistsCheck == True:
                        #         conversionlistsOK = True
                        #         print("conversionlists.py working.")
                        #         pool.imap_unordered(startProcessing, getPDFsInFolder(pdfFolderLocation))
                        #     elif type(conversionlistsCheck) == Exception:
                        #         conversionlistsOK = False
                        #         appendToDebugLog("Error in conversionlists.json!", **{"Error: ":conversionlistsCheck})
                        #         break
                        # if conversionlistsOK == True and x == 1 and filename[-3:] == 'pdf':
                        #     fileloc = pdfFolderLocation+filename[:-len(filename.split("\\")[-1])]
                        #     if '\\' not in filename:
                        #         pool.imap_unordered(startProcessing, [[fileloc, filename]])
                        #     elif filename[:5] == 'Debug':
                        #         pool.imap_unordered(startProcessing, [[fileloc, filename[6:]]])
                else:
                    print('dir handle closed  ')
            # elif rc == win32event.WAIT_OBJECT_0+1:
            #     win32event.SetWaitableTimer(timerHandle, int(0-TimeBetweenCheckins), 0, None, None, True)    # sets of 100 nanoseconds. -10,000,000 = 1 second
            #     print("Checking in!       ")
            #     if enableSlackPosts == True:
            #         requests.post(slackURL,json={'text':"{}: Checking-in.".format(time.strftime("%a, %b %d"))},headers={'Content-type':'application/json'})

            print('Watching for files.', end='\r')
    except Exception as exc:
        print("main() failed: ",str(exc.args))

pdfProcessingData = PDFProcessingSettingsObj()

if __name__ == "__main__":
    p = multiprocessing.Pool()
    # PDFSplitter("C:/tmpp/","TRKINV_20200527 (3).pdf", p)
    main(p)
