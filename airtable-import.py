#   This thing could really use a re-write. It needs a Truck class, with each instance of a truck being created from
# the information in Airtable. New information from PDFs would get incorporated into the list of instances and then
# pushed back up to Airtable.
version = '0.9.0'

import re, os.path, subprocess, time, importlib, sys
import win32file, win32con, win32event, win32net, pywintypes
import json, requests, multiprocessing, configparser
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
UnsplitTRKINVFolder = config['Paths']['unsplit_trkinv_folder']
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

sys.path.append(SettingsFolder)                                     # Give script a path to find conversionlists.py

AirtableAPIHeaders = {
    "Authorization":str("Bearer "+airtableAPIKey),
    "User-Agent":"Python Script",
    "Content-Type":"application/json"
}


class convlists(object):
    def __init__(self):
        import conversionlists
        self.conversionlists = conversionlists
        self.update()
    def update(self):
        try:
            time.sleep(1)
            import conversionlists
            importlib.reload(conversionlists)
            from conversionlists import headerConversionList, dealerCodes, ignoreList, mainRegex, distinctInfoRegex, distinctInfoList, make, status
            self.headerConversionList = headerConversionList
            self.dealerCodes = dealerCodes
            self.ignoreList = ignoreList
            self.mainRegex = mainRegex
            self.distinctInfoRegex = distinctInfoRegex 
            self.distinctInfoList = distinctInfoList
            self.make = make
            self.status = status
        except Exception as exc:        
            return exc              # if conversionlists.py could not be loaded, move files to Errored and update the Debug log with the error
        else:                       # if no errors in reloading conversionlists.py, update cache and run!
            return True


class document(object):

    def __init__(self, fileParentFolder, fileName):
        self.fileName = fileName
        self.location = fileParentFolder
        self.orderNumber = None
        time.sleep(.5)
        attempt = 0
        while True:
            try:
                self.numberOfPages = PDFReader(self.location+self.fileName).getNumPages()
                break
            except:
                attempt += 1
                if attempt > 60:
                    break
                else:
                    time.sleep(.3)
        self.fileText = getPDFText(fileParentFolder+fileName)
        self.fileType = "Unknown"
        self.determineFileType()
        self.sendType = ''
        self.containsMultipleInvoices = False
        self.inDebugFolder = False
        if str(self.location[-6:-1]) == "Debug":
            self.inDebugFolder = True
            writefile(self.fileText, DebugFolder, self.fileName[:-4]+" (debug-pdftotext).txt")
            appendToDebugLog("Debug ran. ",**{"File Name":self.fileName, "File Type":self.fileType})

        if self.fileType == "Unknown":
            moveToFolder(self.location, self.fileName, ErroredFolder)
            appendToDebugLog("File type unknown. ", **{"File Name":self.fileName})
        elif self.fileType == "Supplement":
            moveToFolder(self.location, self.fileName, SuspendedFolder) #move outside of class, implement check for appending to PDF (if doesn't exist in PDF already)
        elif self.checkIfSplitRequired(self.fileText) == True:
            self.containsMultipleInvoices = True
            print("Multiple invoices!")
        else:
            self.loadVariables()
            self.records = {"records":self.getRecords()}

    def loadVariables(self):
        var.update()
        self.mainRegex = var.mainRegex[self.fileType]
        self.distinctInfoRegex = var.distinctInfoRegex[self.fileType]
        self.distinctInfoList = var.distinctInfoList[self.fileType]
        self.make = var.make[self.fileType]
        self.status = var.status[self.fileType]

    def determineFileType(self):
        if self.fileText.count('\n') > 5:
            line1 = self.fileText.split('\n', 1)[0]                 # first line of .txt file
            line2 = self.fileText.split('\n', 2)[1]                 # second line of .txt file
            line5 = self.fileText.split('\n', 5)[4]                 # 5th line
            if "Welcome to Volvo" in line1:
                self.fileType = "Volvo"
            elif "GSO:" in line2:
                self.fileType = "Mack"
            elif "SUPPLEMENT" in line5 and self.numberOfPages == 1:
                self.fileType = "Supplement"
            elif "MACK TRUCKS, INC." in line1:
                self.fileType = "MackInvoice"
            elif "PAGE  1" in line1 or "PAGE 1" in line1:
                self.fileType = "VolvoInvoice"
        # else:
        #     print("Unknown format.")
        #     self.fileType = "Unknown"

        return self.fileType

    def checkIfSplitRequired(self, fileText):
        if len(re.findall(r'Order Number', self.fileText)) > 1 or len(re.findall(r'PAGE {,2}1\D', self.fileText)) > 1 or len(re.findall(r'SUPPLEMENT\n|CONCESSION\n',self.fileText)) > 1: # if it contains 'Order Number' or 'PAGE 1' more than once, it probably contains multiple documents
            return True
        else:
            return False

    def getRecords(self):                                          #       Takes the file and processes it to take out the relevant information
        fieldEntries = {}                                       #   according to which vendor it came from, then returns the fields for
        fields = [{"fields":fieldEntries}]                      #   further formatting, to be uploaded using the Airtable API

        RegexMatches = re.findall(self.mainRegex, self.fileText)
        distinctInfo = re.findall(self.distinctInfoRegex, self.fileText)
        if self.inDebugFolder == True:
            writefile(RegexMatches, DebugFolder, self.fileName[:-4]+" (debug-regexmatches).txt")
        for n, x in enumerate(distinctInfo[0]):
            fieldEntries[self.distinctInfoList[n]] = x
        for x in RegexMatches:
            if x[0] in var.headerConversionList and x[1] not in var.ignoreList:
                fieldEntries.update(runRegExMatching(x, var.headerConversionList))

        if 'Order Number' not in fieldEntries:
            try:
                fieldEntries['Order Number'] = re.search(r'(\d{6,8})', self.fileName).group(1)
            except:
                pass
        
        if 'Dealer Code' in fieldEntries:
            if fieldEntries['Dealer Code'] in var.dealerCodes:
                loc = var.dealerCodes[fieldEntries['Dealer Code']]
                fieldEntries.update({"Location":loc})
        fieldEntries["Make"] = self.make
        if 'Order Number' in fieldEntries:
            self.orderNumber = fieldEntries['Order Number']
            record = getRecord(fieldEntries['Order Number'])
            print(record)
            if record == None:
                self.sendType = "Post"
                fieldEntries["Status Paste"] = self.status
            else:
                self.sendType = "Update"
                fields[0].update({"id":record['id']})
                statusP = record['fields']['Status Paste']
                if statusP == 'on order':
                    fieldEntries["Status Paste"] = self.status
                elif statusP == 'in stock' and self.status != 'on order':
                    fieldEntries["Status Paste"] = self.status
                elif statusP == 'on order - sold' or statusP == 'in stock - sold' or statusP == 'DEMO':
                    pass

            

            OrderOrInvoice = ''
            if self.status == "on order":                  # Order means the truck has been ordered but is not yet available (O)
                OrderOrInvoice = "Order - "
            elif self.status == "in stock":                # Invoice means the truck has been made an is available (A)
                OrderOrInvoice = "Invoice - "
            newName = OrderOrInvoice+self.orderNumber+'.pdf'
            moveToFolder(self.location,self.fileName, self.location, newName)
            self.fileName = newName
            return fields

        else:
            appendToDebugLog("Could not find order number. ", **{"File Name":self.fileName})

    def splitPDF(self):
        lastPageNum = 0
        mostRecentGroup = ''
        pageGroups = {}
        doc = PDFReader(self.location+self.fileName)

        if self.inDebugFolder == True:
            return

        for pdfPageNum, pageObject in enumerate(doc.pages, 1):
            text = getPDFText(self.location+self.fileName, pdfPageNum)
            invPageNum = re.search(r'PAGE {,2}(\d+)', text)
            isMack = False
            creditMemo = False
            sup = None
            first6Lines = ''.join(z for z in text.split('\n')[:6])
            try:
                if "SUPPLEMENT" in first6Lines:
                    sup = 'Supplement'
                elif "CONCESSION" in first6Lines:
                    sup = 'Concession'
                elif "MACK TRUCKS, INC." in first6Lines:
                    isMack = True
                    if "CREDIT MEMO" in first6Lines:
                        creditMemo = True
                if sup != None:
                    invoiceNumberRegex = re.search(r'(?:VEHICLE I.D. NBR: |VEH. ID. NO.: ).*?(\d{6})', text)
                    if invoiceNumberRegex == None:              # Skip Supplement pages that do not contain a vehicle ID number.
                        continue
                    invoiceNumber = invoiceNumberRegex.group(1)
                    supplementLocation = SuspendedFolder+sup+' - '+invoiceNumber+'.pdf'
                    if Path(supplementLocation).exists():
                        olddata = PDFReader(supplementLocation)
                        with open(supplementLocation, 'wb') as updatedPDF:
                            newFile = PDFWriter()
                            newFile.appendPagesFromReader(olddata)
                            newFile.addPage(pageObject)
                            newFile.write(updatedPDF)
                    else:
                        with open(supplementLocation, 'wb') as updatedPDF:
                            newFile = PDFWriter()
                            newFile.addPage(pageObject)
                            newFile.write(updatedPDF)
                elif invPageNum != None:                           # Volvo invoices have page numbers. If the page number goes up, you have a Volvo invoice.
                    if int(invPageNum.group(1)) > lastPageNum:
                        if int(invPageNum.group(1)) == 1:
                            invoiceNumber = re.search(r'(?:VEHICLE I.D. NBR: |VEH. ID. NO.: ).*?(\d{6})', text).group(1)
                            pageGroups[invoiceNumber] = pageGroup('Volvo',pageObject)
                            mostRecentGroup = invoiceNumber
                        else:
                            pageGroups[mostRecentGroup].addPage(pageObject)
                        lastPageNum += 1
                    else:
                        invoiceNumber = re.search(r'(?:VEHICLE I.D. NBR: |VEH. ID. NO.: ).*?(\d{6})', text).group(1)
                        pageGroups[invoiceNumber] = pageGroup('Volvo',pageObject)
                        mostRecentGroup = invoiceNumber
                        lastPageNum = 1
                elif isMack == True:
                    MackOrderNum = re.search(r'\D(\d{8})\D', text)

                    # if MackOrderNum == None:
                    #     appendToDebugLog("Could not find order number for Mack invoice when splitting PDF!")
                    #     writefile(text, DebugFolder, str(time.time())+' missing order number.txt')
                    #     continue
                    if creditMemo == True:
                        if MackOrderNum != None and len(MackOrderNum.groups()) > 0:
                            with open(SuspendedFolder+'Credit Memo - '+MackOrderNum.group(1)+'.pdf', 'wb') as cMemo:
                                newFile = PDFWriter()
                                newFile.addPage(pageObject)
                                newFile.write(cMemo)
                            continue
                        else:
                            oldFile = None
                            if Path(ErroredFolder+'Errored Pages.pdf').exists():
                                oldFile = PDFReader(ErroredFolder+'Errored Pages.pdf')
                            with open(ErroredFolder+'Errored Pages.pdf', 'wb') as err:
                                newFile = PDFWriter()
                                if oldFile != None:
                                    newFile.appendPagesFromReader(oldFile)
                                newFile.addPage(pageObject)
                                newFile.write(err)
                            continue


                    if MackOrderNum != None and len(MackOrderNum.groups()) > 0 and "COMMERCIAL INVOICE" in first6Lines:
                        mostRecentGroup = MackOrderNum.group(1)
                    if mostRecentGroup in pageGroups:
                        pageGroups[mostRecentGroup].addPage(pageObject)
                    else:
                        pageGroups[mostRecentGroup] = pageGroup('Mack',pageObject)
                else:
                    appendToDebugLog("Could not determine page type when splitting.", **{"Contents":text})
                    oldFile = None                                                  # From here
                    if Path(ErroredFolder+'Errored Pages.pdf').exists():
                        oldFile = PDFReader(ErroredFolder+'Errored Pages.pdf')
                    with open(ErroredFolder+'Errored Pages.pdf', 'wb') as err:
                        newFile = PDFWriter()
                        if oldFile != None:
                            newFile.appendPagesFromReader(oldFile)
                        newFile.addPage(pageObject)
                        newFile.write(err)
                    continue                                                        # To here, is a copy of the above. Create function.
            except Exception as exc:
                appendToDebugLog(exc, **{"Is Mack":isMack, "Supplement or Concession":sup, "Contents":text})
                
        print("Now writing invoices.")
        for x in pageGroups:
            try:
                newFile = PDFWriter()
                creditMemo = False

                # if Path(SuspendedFolder+"Credit Memo - "+x+".pdf").exists():        # This section runs fine, but for some reason the Memo doesn't end up in the final PDF. Rewriting soon anyway.
                #     creditMemo = True
                #     oldFile = PDFReader(SuspendedFolder+"Credit Memo - "+x+".pdf")
                #     memoText = getPDFText(SuspendedFolder+"Credit Memo - "+x+".pdf")
                #     memoSearch = re.search(r'INVOICE NET PRICE.*?(?=\d)(\S*?)\n', memoText)
                #     if memoSearch != None and len(memoSearch.groups()) > 0:
                #         if memoSearch.group(1) == pageGroups[x].getNetPrice():
                #             for z in oldFile.pages:
                #                 newFile.addPage(z)
                #                 print(z.extractText())
                #         else:
                #             appendToDebugLog("memoSearch match does not match getNetPrice", **{"memoSearch":memoSearch.group(1), "getNetPrice()":pageGroups[x].getNetPrice()})
                #     else:
                #         appendToDebugLog("No match found for memoSearch", **{"Text":memoText})

                for y in pageGroups[x].pages:
                    newFile.addPage(y)

                if creditMemo == False:
                    name = "Invoice - "
                else:
                    name = "Suspended/Credit Memo - "
                attempts = 0
                while True:
                    try:
                        with open(pdfFolderLocation +name +x +'.pdf', 'wb') as newInvoice:
                            newFile.write(newInvoice)
                            break
                    except:
                        attempts += 1
                        if attempts > 20:
                            raise Exception('Could not open file after 20 attempts (10 seconds)')
                        time.sleep(.5)
            except Exception as exc:
                appendToDebugLog("Could not create file for Invoice Number: "+x)
        moveToFolder(pdfFolderLocation, self.fileName, UnsplitTRKINVFolder)


class pageGroup(object):  # pages variable must be one or more instances of a PyPDF2 page object.
    def __init__(self, docType, pages):
        self.docType = docType
        self.price = 'Unknown'
        if isinstance(pages, list):
            if all(isinstance(x, pdfObj.PageObject) for x in pages):
                self.pages = pages
        elif isinstance(pages, pdfObj.PageObject):
                self.pages = [pages]
        else:
            appendToDebugLog("pageGroup creation failed, did not add PageObject objects when creating class")
            raise Exception("pageGroup creation failed, did not add PageObject objects when creating class")

    def addPage(self, page):
        self.pages.append(page)
    def getNetPrice(self):
        for x in self.pages:
            price = re.search(r'INVOICE NET PRICE.*?(?: |-)(\S*?)\n', x.extractText())
            if price != None and len(price.groups()) > 0:
                self.price = price
                return self.price


        
def getPDFText(filePath, pageToConvert=0):  # pageToConvert=0 means all pages.
    try:
        fileText = subprocess.run([pdftotextExecutable, '-f', str(pageToConvert), '-l', str(pageToConvert), '-nopgbrk', '-simple', '-raw', filePath,'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
    except Exception as exc:
        # try:
        #     os.remove(pdftotextExecutable)
        #     downloadpdftotext()
        # except Exception as exc:
        #     print(exc)
        print("getPDFText() failed: ",str(exc))
        return "Error"
    return fileText
        

def runRegExMatching(content, regexlist):
    columnHeader = regexlist[content[0]]
    preppedData = {}
    if len(columnHeader) > 1:                           # for each pair of header+regex, compute and add values to dictionary
        for x in range(0,len(columnHeader),2):
            search = re.search(columnHeader[x+1],content[1])
            if search != None:
                if len(search.groups()) > 0:            # if it contains one or more groups, create the entry and then append any extra groups to the value
                    preppedData[columnHeader[x]] = search.group(1)
                    if any(search.groups()):            # if anything was matched by a group (and didn't all return None)
                        preppedData[columnHeader[x]] = str()
                        for y in search.groups():
                            if y != None:
                                preppedData[columnHeader[x]] += y
                    else:
                        preppedData[columnHeader[x]] = content[1]
    else:
        preppedData[columnHeader[0]] = content[1]

    return preppedData

def writefile(string, filepath, extension):                 # write file for debugging
    try:
        a = open(filepath+extension, 'w')
        a.write(str(string))
        a.close()
    except PermissionError:
        print("Permission error.")
    except FileExistsError:
        print("File exists.")


def postOrUpdate(content, sendType):
    if sendType == "Post":
        return requests.post(airtableURL,data=None,json=content,headers=AirtableAPIHeaders)
    elif sendType == "Update":
        return requests.patch(airtableURL,data=None,json=content,headers=AirtableAPIHeaders)


def uploadDataToAirtable(content, sendType):                 # uploads the data to Airtable
    if enableAirtablePosts != True:
        return "Airtable connection disabled."
    x = postOrUpdate(content, sendType)
    print("\nPost HTTP code:", x.status_code, "  |   Send type:",sendType)
    if x.status_code == 200:                                 # if Airtable upload successful, move PDF files to Done folder
        print("Success! Sent via "+sendType+"\n")
        return "Success"
    else:
        return {'content':str(content), 'status code: ':str(x.status_code), 'failureText':str(json.loads(x.text)['error']['message'])}

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

def updateAirtableRecordsCache():
    writefile(json.dumps(retrieveRecordsFromAirtable()), mainFolder, 'listofrecords.json')

def loadAirtableRecordsCache():
    with open(mainFolder+'listofrecords.json', 'r') as cache:
        x = str(cache.read())
    return json.loads(x)

def getRecord(orderNumber):
    ListOfAirtableRecords = loadAirtableRecordsCache()
    for x in ListOfAirtableRecords:
        if "Order Number" in x['fields'] and x['fields']['Order Number'] == orderNumber:
            return x


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
    if len(x) == 0:
        return "No files to process."
    pdfFileLocation = x[0]
    pdfFile = x[1]
    start_time = time.time()
    attempts = 0
    while True:                     # Check if file can be accessed (which means it's done being written to the folder)
        try:
            with open(pdfFileLocation+pdfFile, 'rb') as openTest:
                assert openTest.read() != ''     # If it can be read in full (and finds the EOF marker) then it will continue. Otherwise, it will error here and loop again.
                break
        except:
            attempts += 1
            if attempts > 120:
                raise Exception('Could not open file after 120 attempts (over one minute)')
            time.sleep(.5)

    pdf = document(pdfFileLocation, pdfFile)
    
    # print(pdf.orderNumber, pdf.records)

    if pdf.containsMultipleInvoices == True:
        pdf.splitPDF()
        print("Compute time: ", str(time.time()-start_time))
        return
    elif pdf.inDebugFolder == True or enableAirtablePosts != True:             # if it came from the debug folder, move to Done without uploading to Airtable
        moveToFolder(pdfFileLocation, pdf.fileName, DoneFolder) 
        print("Compute time: ", str(time.time()-start_time))
    else:
        # return pdf.records        # return records to main function, so they can be sent to an upload function to be grouped and uploaded (and returned if failed)
        if pdf.orderNumber != None and len(pdf.records['records']) != 0:
            upload = uploadDataToAirtable(pdf.records, pdf.sendType)
            if upload == "Success":
                moveToFolder(pdfFileLocation, pdf.fileName, DoneFolder) 
            else:
                appendToDebugLog("Could not upload to Airtable. ", **{"Order Number":pdf.orderNumber, "Error Message":upload['failureText']})
                writefile("Sent data content: "+upload['content'], DebugFolder, pdf.fileName[:-4]+" (debug-uploadcontent).txt")
                moveToFolder(pdfFileLocation, pdf.fileName, ErroredFolder) 
            print("Compute time: ", str(time.time()-start_time))
            return True
        else:
            moveToFolder(pdfFileLocation, pdf.fileName, ErroredFolder)
            appendToDebugLog("Could not process file.", **{"File Name":pdf.fileName, "File Type":pdf.fileType, "Records":pdf.records})

def getPDFsInFolder(folderLocation):
    filesInFolder = []
    for filename in os.listdir(folderLocation):
        if str(filename)[-3:] == 'pdf':
            filesInFolder.append([folderLocation, filename])
    return filesInFolder

def isdir(x):
    return Path(pdfFolderLocation+x).is_dir()

def makedir(x):
    return Path(pdfFolderLocation+x).mkdir()

class initialize():

    @staticmethod
    def Folder_Check():
        try:                                                    # create folders if they don't exist
            dirlist = ['Debug','Done','Errored','Suspended','Unsplit TRKINV']   
            if isdir(''):
                for x in dirlist:
                    if isdir(x) != True:
                        makedir(x)
            # if Path(pdftotextExecutable).exists() != True:
            #     downloadpdftotext()
            # elif Path(pdftotextExecutable).touch() != True:
            #     appendToDebugLog('Cannot access pdftotext.exe!')
            #     os.remove(pdftotextExecutable)
            #     return False
            return True
        except Exception as exc:
            print("Folder_Check() failed: ",exc.args)
            return False
    
    @staticmethod
    def pdftotext_Check():
        print("Downloading pdftotext")
            


def main(pool):
    try:
        if initialize.Folder_Check() != True:
            print("Folder check failed")
            raise Exception("Folder check failed")

        updateAirtableRecordsCache()
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

        lastCheckTime = 0
        conversionlistsOK = True
        hasTimedOut = False
        while True:

            if hasTimedOut == False:
                win32file.ReadDirectoryChangesW(directoryHandle, buffer, True, flags, overlapped)

            # MultipleObjects so that you can use individual folders. WaitForSingleObject/WaitForMultipleObjects will work as well.
            # Just use WAIT_OBJECT_0 for the first overlapped.hEvent, WAIT_OBJECT_0+1 for the 2nd, 0+2 for the 3rd, etc.
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
                    #print(bits)
                    for x, filename in bufferData:
                        print('Change found: '+filename)
                        if 'conversionlists.py' in filename:
                            if time.time() - lastCheckTime < .5:
                                break
                            lastCheckTime = time.time()
                            conversionlistsCheck = var.update()
                            if conversionlistsCheck == True:
                                conversionlistsOK = True
                                print("conversionlists.py working.")
                                pool.imap_unordered(startProcessing, getPDFsInFolder(pdfFolderLocation))
                            elif type(conversionlistsCheck) == SyntaxError:
                                conversionlistsOK = False
                                appendToDebugLog("Error in conversionlists.py! Did you forget a comma, bracket, brace, or apostrophy on line "+str(int(conversionlistsCheck.args[1][1])-1)+" or "+str(int(conversionlistsCheck.args[1][1]))+"?")
                                break
                            else:
                                appendToDebugLog('Error with conversionlists.py!', **{"Exception Type":type(conversionlistsCheck), "Details":conversionlistsCheck.args})
                                break
                        if conversionlistsOK == True and x == 1 and filename[-3:] == 'pdf':
                            fileloc = pdfFolderLocation+filename[:-len(filename.split("\\")[-1])]
                            if '\\' not in filename:
                                pool.imap_unordered(startProcessing, [[fileloc, filename]])
                            elif filename[:5] == 'Debug':
                                pool.imap_unordered(startProcessing, [[fileloc, filename[6:]]])
                else:
                    print('dir handle closed  ')
            elif rc == win32event.WAIT_OBJECT_0+1:
                win32event.SetWaitableTimer(timerHandle, int(0-TimeBetweenCheckins), 0, None, None, True)    # sets of 100 nanoseconds. -10,000,000 = 1 second
                print("Checking in!       ")
                if enableSlackPosts == True:
                    requests.post(slackURL,json={'text':"{}: Checking-in.".format(time.strftime("%a, %b %d"))},headers={'Content-type':'application/json'})

            print('Watching for files.', end='\r')
# recordcompilation.addRecords(x for x in threads)
# if recordcompilation.send() == False:
#       for x in threads:
#           y = recordcompilation.sendRecord(x)
#           if y != True:
#               movetofolder(originFile(x), "Errored")

    except Exception as exc:
        print("main() failed: ",str(exc.args))


var = convlists()

if __name__ == "__main__":
    p = multiprocessing.Pool()
    main(p)
