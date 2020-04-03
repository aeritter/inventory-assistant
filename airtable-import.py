import re, os.path, subprocess, time, importlib, sys
import win32file, win32con, win32event, win32net, pywintypes
import json, requests, multiprocessing, configparser
from PyPDF2 import PdfFileReader as PDFReader 
from PyPDF2 import PdfFileWriter as PDFWriter
from pathlib import Path
# from airtableconnector import airtable


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
        self.fileText = self.getPDFText(fileName)
        self.fileType = "Unknown"
        self.determineFileType()
        self.sendType = ''
        self.containsMultipleInvoices = False
        self.inDebugFolder = False
        if self.fileType == "Unknown":
            moveToFolder(self.location, self.fileName, ErroredFolder)
            appendToDebugLog("File type unknown.", fileName = self.fileName)
        elif self.fileType == "Supplement":
            moveToFolder(self.location, self.fileName, SuspendedFolder) #move outside of class, implement check for appending to PDF (if doesn't exist in PDF already)
        elif self.checkIfMultipleInvoices(self.fileText) == True:
            self.containsMultipleInvoices = True
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

    def getPDFText(self, filename):
        try:
            fileText = subprocess.run([pdftotextExecutable, '-nopgbrk', '-simple', '-raw', self.location+self.fileName,'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
        except Exception as exc:
            # try:
            #     os.remove(pdftotextExecutable)
            #     downloadpdftotext()
            # except Exception as exc:
            #     print(exc)
            print("getPDFText() failed: ",str(exc))
            return "Error"
        return fileText

    def determineFileType(self):
        if self.fileText.count('\n') > 5:
            line1 = self.fileText.split('\n', 1)[0]                 # first line of .txt file
            line2 = self.fileText.split('\n', 2)[1]                 # second line of .txt file
            line5 = self.fileText.split('\n', 5)[4]                 # 5th line
            if "Welcome to Volvo" in line1:
                self.fileType = "Volvo"
            elif "GSO:" in line2:
                self.fileType = "Mack"
            elif "SUPPLEMENT" in line5:
                self.fileType = "Supplement"
            elif "MACK TRUCKS, INC." in line1:
                self.fileType = "MackInvoice"
            elif "PAGE  1" in line1 or "PAGE 1" in line1:
                self.fileType = "VolvoInvoice"
        # else:
        #     print("Unknown format.")
        #     self.fileType = "Unknown"

        return self.fileType

    def checkIfMultipleInvoices(self, fileText):
        if len(re.findall(r'Order Number', self.fileText)) > 1 or len(re.findall(r'PAGE {,2}3', self.fileText)) > 1: # if it contains 'Order Number' or 'PAGE 3' more than once, it probably contains multiple documents
            return True
        else:
            return False

    def getRecords(self):                                          #       Takes the file and processes it to take out the relevant information
        fieldEntries = {}                                       #   according to which vendor it came from, then returns the fields for
        fields = [{"fields":fieldEntries}]                      #   further formatting, to be uploaded using the Airtable API

        RegexMatches = re.findall(self.mainRegex, self.fileText)
        distinctInfo = re.findall(self.distinctInfoRegex, self.fileText)
        if str(self.location[-6:-1]) == "Debug":
            self.inDebugFolder = True
            writefile(RegexMatches, DebugFolder, self.fileName[:-4]+" (debug-regexmatches).txt")
            writefile(self.fileText, DebugFolder, self.fileName[:-4]+" (debug-pdftotext).txt")
            appendToDebugLog("Debug ran. ",FileName=self.fileName, FileType=self.fileType)
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
            appendToDebugLog("Could not find order number", file=self.fileName)


    def splitPDF(self):
        pageGroups = []
        orderNumbers = []
        if self.fileType == "MackInvoice":
            y = 0
            allmatches = re.findall(r'(?:(Invoice Date)|(Date Printed:)|(Order Number).*?(\d{8}))', self.fileText, flags=re.S)
            for x, page in enumerate(allmatches):
                if x+1 < len(allmatches):
                    if allmatches[x+1][2] != "Order Number":
                        y += 1
                    elif x != 0:
                        pageGroups.append(y)
                        y = 0                       #for multithreading, remove this reset and pass the page numbers directly
                else:                               # [7,7,7] becomes [7,14,21], and then you would pass [[0,7][8,14][15,21]]
                    y += 1
                    pageGroups.append(y)
            for x in allmatches:
                if x[3] != '':
                    orderNumbers.append(x[3])

        elif self.fileType == "VolvoInvoice":
            y = 1
            allmatches = re.findall(r'PAGE {,2}(\d+)', self.fileText, flags=re.S)
            for x, page in enumerate(allmatches):                  # iterate through page numbers
                if x+1 < len(allmatches):
                    if int(page) == 1 and int(allmatches[x+1]) == int(page):
                        y+=1
                    elif int(page) != 1:                                   # if current page number is higher than last seen page number, continue
                        y += 1
                    elif x != 0:
                        pageGroups.append(y)                                # otherwise, add to list and reset counter
                        y = 1
                else:
                    y += 1
                    pageGroups.append(y)
            volvmatches = re.findall(r'PAGE {,2}2.*?SERIAL NBR: (\S{6})', self.fileText, flags=re.S)
            for x in volvmatches:
                orderNumbers.append(x)

        pageCounter = 0
        pageGroupNum = 0
        moveToFolder(pdfFolderLocation, self.fileName, UnsplitTRKINVFolder)
        readOldFile = PDFReader(UnsplitTRKINVFolder+self.fileName)
        for y, z in enumerate(pageGroups):                          # can probably be multithreaded
            newFile = PDFWriter()
            if z > 1:
                for x in range(0, z):
                    newFile.addPage(readOldFile.getPage(pageCounter))
                    pageCounter += 1
                with open(pdfFolderLocation+'Invoice - '+orderNumbers[pageGroupNum]+'.pdf', 'wb') as newpdf:
                    newFile.write(newpdf)
                pageGroupNum += 1
            else:
                pageCounter += 1
        

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
            if enableAirtablePosts != True:
                return "Airtable connection disabled."
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


def appendToDebugLog(errormsg, **kwargs):
    print(errormsg)
    errordata = str(" Error: "+errormsg+', '.join('{0}: {1!r}'.format(x, y) for x, y in kwargs.items()))
    try:
        a = open(DebugFolder+"Debug log.txt", "a+")
        a.write("\n"+str(time.ctime())+errordata)
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
            with open(pdfFileLocation+pdfFile, 'r'):
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
        return None
    elif pdf.inDebugFolder == True:             # if it came from the debug folder, move to Done without uploading to Airtable
        moveToFolder(pdfFileLocation, pdf.fileName, DoneFolder) 
        print("Compute time: ", str(time.time()-start_time))
    else:
        # return pdf.records        # return records to main function, so they can be sent to an upload function to be grouped and uploaded (and returned if failed)
        if pdf.orderNumber != None and len(pdf.records['records']) != 0:
            upload = uploadDataToAirtable(pdf.records, pdf.sendType)
            if upload == "Success":
                moveToFolder(pdfFileLocation, pdf.fileName, DoneFolder) 
            else:
                appendToDebugLog("Could not upload ", OrderNumber = pdf.orderNumber, ErrorMessage=upload['failureText'])
                writefile("Sent data content: "+upload['content'], DebugFolder, pdf.fileName[:-4]+" (debug-uploadcontent).txt")
                moveToFolder(pdfFileLocation, pdf.fileName, ErroredFolder) 
            print("Compute time: ", str(time.time()-start_time))
            return True
        else:
            moveToFolder(pdfFileLocation, pdf.fileName, ErroredFolder)
            appendToDebugLog("Could not process file.", FileName=pdf.fileName, FileType=pdf.fileType, Records=pdf.records)

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
        print("Waiting for files.")

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
                        print(filename)
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
                                appendToDebugLog('Error with conversionlists.py!', ExceptionType=type(conversionlistsCheck), Details=conversionlistsCheck.args)
                                break
                        if conversionlistsOK = True and x == 1 and filename[-3:] == 'pdf':
                            fileloc = pdfFolderLocation+filename[:-len(filename.split("\\")[-1])]
                            if '\\' not in filename:
                                pool.imap_unordered(startProcessing, [[fileloc, filename]])
                            elif filename[:5] == 'Debug':
                                pool.imap_unordered(startProcessing, [[fileloc, filename[6:]]])
                else:
                    print('dir handle closed')
            elif rc == win32event.WAIT_OBJECT_0+1:
                win32event.SetWaitableTimer(timerHandle, int(0-TimeBetweenCheckins), 0, None, None, True)    # sets of 100 nanoseconds. -10,000,000 = 1 second
                print("Checking in!")
                if enableSlackPosts == True:
                    requests.post(slackURL,json={'text':"{}: Checking-in.".format(time.strftime("%a, %b %d"))},headers={'Content-type':'application/json'})

            print('Watching for files.')
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
