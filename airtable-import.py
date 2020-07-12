version = '1.0.0'

import re, os.path, subprocess, time, importlib, sys, urllib.parse
import win32file, win32con, win32event, win32net, pywintypes        # watchdog can probably replace all these (pip install watchdog)
import json, requests, multiprocessing, threading, queue, configparser
import fitz # fitz = PyMuPDF
from PyPDF2 import PdfFileReader as PDFReader 
from PyPDF2 import PdfFileWriter as PDFWriter
from PyPDF2 import pdf as pdfObj
from pathlib import Path

lock = threading.Lock()
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
SettingsFolder = config['Paths']['settings_folder']
OriginalDocsFolder = config['Paths']['original_docs_folder']
DocumentsFolder = config['Paths']['documents_folder']
pdftotextExecutable = SettingsFolder+"/pdftotext.exe"

airtableURLFields = ""
airtableURL = config['Other']['airtable_url']
slackURL = config['Other']['slack_url']
airtableAPIKey = config['Other']['airtable_api_key']
readDirTimeout = int(config['Other']['read_dir_timeout'])*1000     # *1000 to convert milliseconds to seconds
debug = config['Other'].getboolean('enable_debug')
enableAirtablePosts = config['Other'].getboolean('enable_airtable_posts')
enableSlackPosts = config['Other'].getboolean('enable_slack_posts')
enableSlackStatusUpdate = config['Other'].getboolean('enable_status_update')
CheckinHour = int(float(config['Other']['check-in_hour'])*60*60)
TimeBetweenCheckins = float(config['Other']['time_between_check-ins_in_minutes'])*60*10000000 #converted to 100 nanoseconds for the function


AirtableAPIHeaders = {
    "Authorization":str("Bearer "+airtableAPIKey),
    "User-Agent":"Python Script",
    "Content-Type":"application/json"
}


reSearchInvoiceNum = re.compile(r'(?<= )\d{7}(?= |\n)|\d{2}/\d{5}')     #NOTE: Needs to be moved to pdfProcessingSettings.json


class outputs(object):
    def __init__(self):
        self.out = {"airtable":AirtableUpload()}
    def send(self, invobj, source):
        for x in self.out:
            if x != source:
                self.out[x].send(invobj)

# class inputs(object):     # in progress


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
        text = self.getText()

        def findSpecsRecursively(section, txt, parent=0):
            specs = {}
            # Fits my dataset, but likely missing parts that should work for other datasets (ex. using multiline regex with both a Match and a Search)
            # Need to better define process priority.
            if "Defaults" in section:
                specs.update(section["Defaults"])
            if "Search" in section:
                value = section["Search"]
                if type(value) == str:
                    if value not in pdfProcessingData.data["SearchLists"]:
                        appendToDebugLog("pdfProcessingSettings missing entry in SearchLists.", **{"List name":value})
                    else:
                        for x in pdfProcessingData.data[value]:
                            specs.update(findSpecsRecursively(x, txt))
                elif type(value) == list:
                    for x in value:
                        specs.update(findSpecsRecursively(x, txt))
            if "Regex" in section:
                if "Multiline" in section and section["Multiline"] == 1:
                    result = section["Regex"].findall(txt)
                    if "Match" in section:
                        if type(section["Match"]) == str and section["Match"] in pdfProcessingData.data["MatchLists"]:
                            for x in result:
                                if x[0] in pdfProcessingData.data["MatchLists"][section["Match"]]:
                                    for y in pdfProcessingData.data["MatchLists"][section["Match"]][x[0]]:
                                        specs.update(findSpecsRecursively(y, x[1]))
                    #elif 
                if "Category" in section:
                    if section["Regex"] == 1:
                        result = txt
                    elif type(section["Regex"]) == re.Pattern:
                        result = section["Regex"].search(txt)
                        if result != None and len(result.groups()) > 0:
                            result = result.group(1)
                        else:
                            return specs
                    if "Replace" in section:
                        if type(section["Replace"]) == str and section["Replace"] in pdfProcessingData.data["ReplaceLists"]:
                            if result in pdfProcessingData.data["ReplaceLists"][section["Replace"]]:
                                result = pdfProcessingData.data["ReplaceLists"][section["Replace"]][result]
                        elif type(section["Replace"]) == dict:
                            if result in section["Replace"]:
                                result = section["Replace"][result]
                    specs[section["Category"]] = result
            return specs

        if self.docType in pdfProcessingData.data["fileTypes"]:
            procSet = pdfProcessingData.data["fileTypes"][self.docType]
            try:
                return findSpecsRecursively(procSet, text)
            except Exception as exc:
                appendToDebugLog("Could not find specs, something went wrong.", **{"Error":exc})



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
    def __init__(self):
        self.inventory = {}             # dictionary of inventory UIDs and the corresponding inventory object eg. {"12345":inventoryObject()}
        self.unknownDocs = {}           # format = {"docInvID":[docObj1, docObj2]}
        self.lastUpdated = time.time()
        self.output = outputs()
        global airtableURLFields
        for x in retrieveRecordsFromAirtable(airtableURLFields):
            if "Order Number" in x['fields']:
                stockNo = x['fields']['Order Number']       # NOTE: Change from Order Number to Stock Number once applicable.
                t = inventoryObject(stockNo)
                t.airtableRefID = x['id']
                t.specs = x['fields']
                self.inventory[stockNo] = t
            else:
                appendToDebugLog("No Order Number found for Airtable record.", **{"ID":x['id']})

    def addInvObjToInventory(self, newInvObj, source):
        self.lastUpdated = time.time()
        if newInvObj.uniqueIdentifier in self.inventory:
            print("Inventory object exists: "+str(newInvObj.uniqueIdentifier))
            oldInvObj = self.inventory[newInvObj.uniqueIdentifier]

            # add documents from incoming inventory object to existing inventory object if they do not currently exist there
            if newInvObj.documents != None:
                for x in newInvObj.documents:
                    # Compare between the new documents and the old documents, using a list of the contents of each page object's dictionary.
                    found = False
                    for y in oldInvObj.documents:
                        for c in y.__dict__['pages']:
                            for z in x.__dict__['pages']:
                                if z.__dict__ == c.__dict__:
                                    found = True
                    if found == False:
                        print("New doc added to inventory object: "+oldInvObj.uniqueIdentifier)
                        oldInvObj.documents.append(x)
            
            # add incoming specs to existing inventory object
            if newInvObj.specs != None:
                if oldInvObj.specs == None:
                    oldInvObj.specs = newInvObj.specs
                else:
                    oldInvObj.specs.update(newInvObj.specs)
                self.output.send(oldInvObj, source)

        else:
            self.inventory[newInvObj.uniqueIdentifier] = newInvObj
            self.output.send(self.inventory[newInvObj.uniqueIdentifier], source)
            # print("Created Inventory object: "+str(newInvObj.uniqueIdentifier))
                
    
    
class PDFProcessingSettingsObj(object):
    def __init__(self):
        self.operations = ["Search", "Replace", "Findall", "Match", "Properties", "ReplaceList"]
        self.fileData = {}  # Unprocessed settings
        self.data = {}      # Settings with RegEx strings converted from a string to re.compile()
        self.loadFromFile()
        self.update()

    def loadFromFile(self):
        try:
            time.sleep(.1)
            with open(SettingsFolder+"pdfProcessingSettings.json", 'r') as clist:
                self.fileData = json.load(clist)
        except Exception as exc:        
            appendToDebugLog("Could not update from pdfProcessingSettings.json", **{"Error":exc})

    def update(self):
        self.data = dict(self.fileData)
        fields = set()
        def recursiveUpdate(part):
            if type(part) == list:
                for x in part:
                    recursiveUpdate(x)  
            elif type(part) == dict:
                for name, value in part.items():
                    if name == "Defaults":
                        for x in value:
                            fields.add(x)
                    elif name == "Category":
                        fields.add(value)
                    elif name == "Regex" and type(value) == str:
                        if "Multiline" in part.keys() and part["Multiline"] == 1:
                            part[name] = re.compile(value, re.M)
                        else:
                            part[name] = re.compile(value, re.S)
                    elif name == "Search" and type(value) == list:
                        recursiveUpdate(value)
                    elif name == "Match" and type(value) == dict:
                        for x in value:
                            recursiveUpdate(value[x])

        for x in self.data["fileTypes"].values():
            recursiveUpdate(x)
        for x in self.data["MatchLists"].values():
            for y in x.values():
                recursiveUpdate(y)
        
        # Set the fields used for pulling data from Airtable to the ones we have defined in the processing settings,
        # This is to ensure only editable fields get placed in the specs of an Inventory object
        # otherwise we will encounter errors when outputting to Airtable.
        global airtableURLFields
        airtableURLFields = "?"+"&".join("fields%5B%5D={}".format(urllib.parse.quote(x)) for x in fields)



class AirtableUpload(object):
    def __init__(self):
        self.entries = queue.Queue()
        self.trigger = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        self.lastSendTime = time.time()
        self.updateList = []
        self.postList = []

    def send(self, entry):
        self.entries.put(entry)
        self.trigger.set()
        self.trigger.clear()

    def upload(self, sendType, content):
        if sendType == "Patch":
            response = requests.patch(airtableURL, data=None, json={"records":[ent.formatForAirtableUpdate() for ent in content]}, headers=AirtableAPIHeaders)
        elif sendType == "Post":
            response = requests.post(airtableURL, data=None, json={"records":[ent.formatForAirtableCreate() for ent in content]}, headers=AirtableAPIHeaders)

        if response.status_code != 200:
            if len(content) == 1:
                appendToDebugLog("Airtable upload failed.", **{"Error":response.text, "Request Type":sendType, "Order Number":content[0].specs["Order Number"]})
            else:
                for x in content:
                    self.upload(sendType, [x])


    def loop(self):
        while True:
            lprint("Airtable uploading process ready for entries to upload.")
            if self.entries.qsize() == 0:
                self.trigger.wait()
            x = 0
            while x < 10:
                time.sleep(0.22)    # time between uploads to Airtable
                if self.entries.qsize() > 0:
                    x = 0
                    try:
                        update = []
                        create = []
                        while len(update) < 10 and len(create) < 10 and self.entries.qsize() > 0:
                            z = self.entries.get()
                            if z.airtableRefID:
                                update.append(z)
                            else:
                                create.append(z)

                        # Need to consolidate these two into a single function
                        if len(update) > 0:
                            self.upload("Patch", update)
                            lprint("Uploaded to Airtable: "+str([ent.uniqueIdentifier for ent in update]))
                        time.sleep(.2)
                        if len(create) > 0:
                            self.upload("Post", create)
                            lprint("Created in Airtable: "+str([ent.uniqueIdentifier for ent in create]))


                    except Exception as exc:
                        appendToDebugLog("Something happened while retrieving data from the Airtable upload queue.", **{"Error":exc})

                # Increment x if nothing left in the queue so we can eventually exit the loop once it's no longer useful to stay in it.
                else:
                    x += 1



def getPDFText(filePath, pageToConvert=0):  # pageToConvert set to 0 will convert all pages.
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


def lprint(st):     # NOTE: Worth it to use for all print statements?
    lock.acquire()
    print(st)
    lock.release()


def retrieveRecordsFromAirtable(airtableURLFields="", offset=None):
    while True:
        try:
            # if enableAirtablePosts != True:
            #     return "Airtable connection disabled."
            if offset == None:
                x = requests.get(airtableURL+airtableURLFields, data=None, headers=AirtableAPIHeaders)
            else:
                x = requests.get(airtableURL+airtableURLFields+"{}offset={}".format("?" if airtableURLFields == "" else "&", offset), data=None, headers=AirtableAPIHeaders)

            records = x.json()['records']
            if 'offset' in json.loads(x.text):
                records.extend(retrieveRecordsFromAirtable(offset=json.loads(x.text)['offset']))
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
    pdfPageList = [page(x) for x in getPDFText(pdfLocation+pdfFilename).split('\f')[:-1]]  #last entry will always be empty, as the document will always end with a \f value (formfeed character)
    print("Done making page objects from pdftotext.exe")
    ctime = time.time()

    # Error out if the number of pages found between PyMuPDF and pdftotext.exe do not match.
    if doc.pageCount != len(pdfPageList):
        appendToDebugLog("Number of page objects does not equal number of pages found after text conversion", **{"Document":pdfLocation+pdfFilename})
        return

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
    def writePDFfromSplitter(doc, location):
        attempt = 0
        while True:
            try:
                doc.save(location)
                doc.close()
                break
            except Exception as exc:
                attempt += 1
                if attempt > 10:
                    appendToDebugLog("Couldn't save after 10 attempts.", **{"Location":location, "Error":exc})
                time.sleep(1)
                print("Error saving: "+location)
    writethreads = [threading.Thread(target=(writePDFfromSplitter), args=([docs[z], pageGroups[z].location])) for z in docs]
    for thread in writethreads:
        thread.start()
    for thread in writethreads:
        thread.join()

    # Send document objects back to main() so inventory objects can be created and sent to the database.
    print("Time taken to split PDF after pdftotext.exe: "+str(time.time()-ctime))
    doc.close()
    return pageGroups



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
        

        # NOTE: need initialization phase to populate internal database and ensure folder structure and all necessary files exist
        # NOTE: need reconciliation phase to ensure all outputs contain the latest data

        db = datastore()

        flags = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
        directoryHandle = win32file.CreateFile(pdfFolderLocation, 0x0001,win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
        startTime = time.localtime()
        initialCheckinTimeConverted = int(float((86400-(startTime.tm_hour*60*60+startTime.tm_min*60+startTime.tm_sec)+CheckinHour)*10000000))
        timerHandle = win32event.CreateWaitableTimer(None, True, None)
        win32event.SetWaitableTimer(timerHandle, int(0-initialCheckinTimeConverted), 0, None, None, True)
        overlapped = pywintypes.OVERLAPPED()
        overlapped.hEvent = win32event.CreateEvent(None, 0, 0, None)
        buffer = win32file.AllocateReadBuffer(8192)

        print("Waiting for files.")

        hasTimedOut = False
        while True:
            if hasTimedOut == False:
                win32file.ReadDirectoryChangesW(directoryHandle, buffer, True, flags, overlapped)

            rc = win32event.MsgWaitForMultipleObjects([overlapped.hEvent, timerHandle], False, readDirTimeout, win32event.QS_ALLEVENTS)
            if rc == win32event.WAIT_TIMEOUT:
                hasTimedOut = True
                print(time.ctime(),' Wait timeout.')
                pool.imap_unordered(startProcessing, getPDFsInFolder(pdfFolderLocation))
            elif rc == win32event.WAIT_OBJECT_0:
                hasTimedOut = False
                result = win32file.GetOverlappedResult(directoryHandle, overlapped, True)
                if result:
                    bufferData = win32file.FILE_NOTIFY_INFORMATION(buffer, result)
                    for x, filename in bufferData:

                        fileloc = pdfFolderLocation+filename[:-len(filename.split("\\")[-1])]
                        if x == 1 and filename[-3:] == 'pdf' and '\\' not in filename:
                            print('File found, processing: '+filename)
                            docs = list(item for item in pool.imap_unordered(startProcessing, [[fileloc, filename]]))[0].values()
                            
                            for y in docs:
                                specs = y.getSpecs()
                                if "Order Number" in specs:
                                    z = inventoryObject(specs["Order Number"])
                                    z.documents.append(y)
                                    z.specs = specs
                                    db.addInvObjToInventory(z, "document")
                                elif y.docType == "Supplement":
                                    if "ID" in specs and "Model" in specs:
                                        UID = str(specs["Model"]+specs["ID"])
                                        matchFound = False
                                        for invObj in db.inventory.values():
                                            if "VIN" in invObj.specs and "Model" in invObj.specs:
                                                if str(invObj.specs["Model"]+invObj.specs["VIN"][-6:]) == UID:
                                                    print("UID Matched!")
                                                    invObj.documents.append(y)
                                                    matchFound = True
                                                    break
                                        if matchFound == False:
                                            print("UID Match not found for "+UID)
                                            if UID in db.unknownDocs:
                                                db.unknownDocs[UID].append(y)
                                            else:
                                                db.unknownDocs[UID] = [y]

                            # Move original PDF away
                            moveToFolder(fileloc, filename, OriginalDocsFolder)
                else:
                    print('dir handle closed  ')

            elif rc == win32event.WAIT_OBJECT_0+1:
                win32event.SetWaitableTimer(timerHandle, int(0-TimeBetweenCheckins), 0, None, None, True)    # sets of 100 nanoseconds. -10,000,000 = 1 second
                print("Checking in!       ")
                if enableSlackPosts == True:
                    requests.post(slackURL,json={'text':"{}: Checking-in.".format(time.strftime("%a, %b %d"))},headers={'Content-type':'application/json'})

            print('Watching for files.', end='\r')
    except Exception as exc:
        print("main() failed: ",str(exc.args))

pdfProcessingData = PDFProcessingSettingsObj()

if __name__ == "__main__":
    p = multiprocessing.Pool()
    main(p)
