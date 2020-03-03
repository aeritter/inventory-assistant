import re, os.path, subprocess, time
import json, requests, multiprocessing
from PyPDF2 import PdfFileReader as PDFReader 
from PyPDF2 import PdfFileWriter as PDFWriter

debug = True

mainFolder = 'C:\\airtabletest\\'

with open(mainFolder+'api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open(mainFolder+'url.txt', 'r') as url:         #      Location of .txt file containing URL for the table in Airtable 
    url = url.read()                                 #   (found in api.airtable.com, not the same as the URL you see when browsing)

pdfFolderLocation = mainFolder+'python-test\\'       # location of .pdf files
pdftotextExecutable = mainFolder+'pdftotext.exe'         # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)

from conversionlists import headerConversionList, dealerCodes, ignoreList

AirtableAPIHeaders = {
    "Authorization":str("Bearer "+api_key),
    "User-Agent":"Python Script",
    "Content-Type":"application/json"
}

mainRegex = {   
    "Mack":re.compile(r'^(?:   \S{6} {2,6}| {3,5})(?: |(.{2,32})(?<! ) +(.*)\n)', flags=re.M), 
    "Volvo":re.compile(r'^ {3,6}(\S{3})\S{3} +. +. +(.*?)(:?  |\d\.\d\n)', flags=re.M), 
    "MackInvoice":re.compile(r'^ (\S{3})\S{4} +(.*?)  ', flags=re.M), 
    "VolvoInvoice":re.compile(r'^(\S{3})\S{4} +(.*?)  ', flags=re.M)
    }
specificInfoRegex = {
    "Mack":re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n.*?Model Year:(\w+)', flags=re.S), 
    "Volvo":'', 
    "MackInvoice":re.compile(r'Order Number.*?(\S{4,5}) +(\d{8}).*?VIN #.*?(\S{17}) ', flags=re.S), 
    "VolvoInvoice":re.compile(r'DEALER\..*?(\S{5}) +.*?NBR:.*?(\S{17}).*? SERIAL NBR: (\S{6})', flags=re.S)
}
uniqueInfoList = {
    "Mack":['Model','GSO','Chassis Number','Model Year'],
    "Volvo":[], 
    "MackInvoice":['Dealer Code','Order Number','Full VIN'], 
    "VolvoInvoice":['Dealer Code','Full VIN','Order Number']
}
make = {
    "Mack":"Mack",
    "Volvo":"Volvo",
    "MackInvoice":"Mack",
    "VolvoInvoice":"Volvo"
}
status = {
    "Mack":"O",
    "Volvo":"O",
    "MackInvoice":"A",
    "VolvoInvoice":"A"
}


class document(object):

    def __init__(self, fileName):
        self.fileName = fileName
        self.orderNumber = ''
        self.fileText = self.getPDFText(fileName)
        self.fileType = self.determineFileType()                                   # looping
        self.sendType = ''
        self.isMultipleInvoices = self.checkIfMultipleInvoices(self.fileText)    # here
        self.debug = True
        if self.isMultipleInvoices == False:
            self.loadVariables()
            self.records = {"records":self.getRecords()}

    def loadVariables(self):
        self.mainRegex = mainRegex[self.fileType]
        self.specificInfoRegex = specificInfoRegex[self.fileType]
        self.uniqueInfoList = uniqueInfoList[self.fileType]
        self.make = make[self.fileType]
        self.status = status[self.fileType]

    def getPDFText(self, filename):
        try:
            fileText = subprocess.run([pdftotextExecutable, '-nopgbrk', '-simple', '-raw', '-marginb','40', pdfFolderLocation+str(filename),'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
        except:
            return "Error"
        return fileText

    def determineFileType(self):        #remove filename
        line1 = self.fileText.split('\n', 1)[0]                 # first line of .txt file
        line2 = self.fileText.split('\n', 2)[1]                 # second line of .txt file
        if "Welcome to Volvo" in line1:
            self.fileType = "Volvo"
        elif "GSO:" in line2:
            self.fileType = "Mack"
        elif "MACK TRUCKS, INC." in line1:
            self.fileType = "MackInvoice"
        elif "PAGE  1" in line1 or "PAGE 1" in line1:
            self.fileType = "VolvoInvoice"
        else:
            print("Unknown format.")
            self.fileType = "Unknown"

        # if self.isMultipleInvoices == True:
        #     self.fileType = "Multiple"

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
        SpecificInfo = re.findall(self.specificInfoRegex, self.fileText)
        if self.debug == True:
            writefile(RegexMatches, pdfFolderLocation+"Debug\\", self.fileName[:-4]+" (debug-regexmatches).txt")
        for n, x in enumerate(SpecificInfo[0]):
            if self.uniqueInfoList[n] in headerConversionList:
                fieldEntries[headerConversionList[self.uniqueInfoList[n]][0]] = x
        for x in RegexMatches:
            if x[0] in headerConversionList and x[1] not in ignoreList:
                fieldEntries.update(runRegExMatching(x, headerConversionList))
        if 'Order Number' in fieldEntries:
            id = getRecordID(fieldEntries['Order Number'])
            if id != None:
                fields[0].update({"id":id})
                self.sendType = "Update"
            else:
                self.sendType = "Post"
        else:
            appendToDebugLog("Could not find order number", extra=str("file - "+self.fileName))
        if 'Dealer Code' in fieldEntries:
            if fieldEntries['Dealer Code'] in dealerCodes:
                loc = dealerCodes[fieldEntries['Dealer Code']]
                fieldEntries.update({"Location":loc})
        fieldEntries["Make"] = self.make
        fieldEntries["Status"] = self.status

        OrderOrInvoice = ''
        if self.status == "O":
            OrderOrInvoice = "Order - "
        elif self.status == "A":
            OrderOrInvoice = "Invoice - "
        newName = OrderOrInvoice+fieldEntries['Order Number']+'.pdf'
        self.fileName = newName
        self.orderNumber = fieldEntries['Order Number']
        moveToFolder([[pdfFolderLocation+self.fileName, newName]], '')

        return fields


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
        moveToFolder([[pdfFolderLocation+self.fileName, self.fileName]],"Unsplit TRKINV")
        readOldFile = PDFReader(pdfFolderLocation+'Unsplit TRKINV\\'+self.fileName)
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

    def moveToDone(self):
        moveToFolder([[pdfFolderLocation+self.fileName, self.fileName]], "Done") 

    def uploadData(self):
        x = uploadDataToAirtable(self.records, self.sendType)
        if x == "Success":
            self.moveToDone()
        else:
            self.createDebugFiles(x)
        return x

    def createDebugFiles(self, content):
        appendToDebugLog("Could not upload.", extra=content)
        

def runRegExMatching(content, regexlist):
    columnHeader = regexlist[content[0]]
    preppedData = {}
    if len(columnHeader) > 1:                           # for each pair of header+regex, compute and add values to dictionary
        for x in range(0,len(columnHeader),2):
            search = re.search(columnHeader[x+1],content[1])
            if search != None:
                if len(search.groups()) > 0:
                    preppedData[columnHeader[x]] = search.group(1)
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
        return requests.post(url,data=None,json=content,headers=AirtableAPIHeaders)
    elif sendType == "Update":
        return requests.patch(url,data=None,json=content,headers=AirtableAPIHeaders)


def uploadDataToAirtable(content, sendType):                                # uploads the data to Airtable
    x = postOrUpdate(content, sendType)
    # print("\n\nPost response: ",x.json())
    print("\nPost HTTP code:", x.status_code)
    if x.status_code == 200:                                 # if Airtable upload successful, move PDF files to Done folder
        print("Success! Sent via "+sendType+"\n")
        return "Success"
    else:
        return {'content':content, 'failureText':x.text}

def retrieveRecordsFromAirtable(offset):
    while True:
        try:
            if offset == None:
                x = requests.get(url+"?fields%5B%5D=Order+Number&fields%5B%5D=Status", data=None, headers=AirtableAPIHeaders)
            else:
                x = requests.get(url+"?fields%5B%5D=Order+Number&fields%5B%5D=Status&offset="+offset, data=None, headers=AirtableAPIHeaders)
        
            records = x.json()['records']
            if 'offset' in json.loads(x.text):
                records.extend(retrieveRecordsFromAirtable(json.loads(x.text)['offset']))
            return records
                
        except ConnectionError:
            print("Could not connect to airtable.com")
            time.sleep(30)

def updateAirtableRecordsCache():
    ListOfAirtableRecords = str(retrieveRecordsFromAirtable(None)).replace("\'","\"") # pull records, convert to str, replace single quotes with double to make json format valid
    writefile(ListOfAirtableRecords, mainFolder, 'listofrecords.json')

def loadAirtableRecordsCache():
    with open(mainFolder+'listofrecords.json', 'r') as cache:
        x = str(cache.read())
    return json.loads(x)

def getRecordID(orderNumber):
    ListOfAirtableRecords = loadAirtableRecordsCache()
    for x in ListOfAirtableRecords:
        if "Order Number" in x['fields'] and x['fields']['Order Number'] == orderNumber:
            return x['id']


def appendToDebugLog(errormsg, **kwargs):
    print(errormsg)
    try:
        a = open(pdfFolderLocation+"Debug\\Debug log.txt", "a+")
        extra = ''
        if 'orderNumber' in kwargs:
            orderNumber = kwargs['orderNumber']
        else:
            orderNumber = 'Unknown'
        if 'extra' in kwargs:
            extra = kwargs['extra']
        a.write(str(time.ctime()+", Order #: "+orderNumber+", Error: "+errormsg+', Extra information: '+str(extra)+'\n'))
        a.close()
    except:
        print("Can't append to debug log file.")


def moveToFolder(filesToMove, folder):      # format: moveToFolder([["C:\\Path\\To\\File.pdf", "File.pdf"]["C:\\etc\\etc.etc", "etc.etc"]], "Errored")
    for x in filesToMove:                   # more: moveToFolder([["Current file path", "New name of file"]], "Subfolder name")
        try:
            os.rename(x[0], pdfFolderLocation+folder+"\\"+x[1])
        except FileExistsError:
            print("File", x[1], "exists in", folder, "folder.")
            try:
                os.rename(x[0], pdfFolderLocation+folder+"\\Already Exists\\"+x[1][:-4]+" (1)"+x[1][-4:])  
            except:
                os.remove(x[0])
                pass
            pass
        except FileNotFoundError:
            print(x[1]+" not found.")
            pass


def startProcessing(x):
    pdf = document(x)

    if pdf.isMultipleInvoices == True:
        pdf.splitPDF()
        return None
    else:
        upload = pdf.uploadData()
        return upload

def checkFolder():
    filesInFolder = []
    for filename in os.listdir(pdfFolderLocation):
        if str(filename)[-3:] == 'pdf':
            filesInFolder.append(filename)
    return filesInFolder

def main(pool, files, **kwargs):
    threads = pool.imap_unordered(startProcessing, files)
                    


if __name__ == "__main__":
    p = multiprocessing.Pool()
    while True:
        ListOfFiles = checkFolder()
        if len(ListOfFiles) > 0:
            updateAirtableRecordsCache()
            main(p, ListOfFiles, iterations=0)
        else:
            print("No files found.")
        time.sleep(10)
