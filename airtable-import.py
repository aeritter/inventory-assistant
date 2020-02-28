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

from conversionlists import headerConversionList, dealerCodes

pdfFolderLocation = mainFolder+'python-test\\'       # location of .pdf files
pdftotextExecutable = mainFolder+'pdftotext.exe'         # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)
mackRegex = re.compile(r'^(?:   \S{6} {2,6}| {3,5})(?: |(.{2,32})(?<! ) +(.*)\n)', flags=re.M)
mackSpecificInfoRegex = re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n.*?Model Year:(\w+)', flags=re.S) # pulls info that doesn't follow the main pattern
mackUniqueInfoList = ['Model','GSO','Chassis Number','Model Year']
volvoRegex = re.compile(r'^ {3,6}(\S{3})\S{3} +. +. +(.*?)(:?  |\d\.\d\n)', flags=re.M)


mackInvoiceRegex = re.compile(r'^ (\S{3})\S{4} +(.*?)  ', flags=re.M)
volvoInvoiceRegex = re.compile(r'^(\S{3})\S{4} +(.*?)  ', flags=re.M)
mackUpdateSpecificInfoRegex = re.compile(r'Order Number.*?(\S{4,5}) +(\d{8}).*?VIN #.*?(\S{17}) ', flags=re.S)
volvoUpdateSpecificInfoRegex = re.compile(r'DEALER\..*?(\S{5}) +.*?NBR:.*?(\S{17}).*? SERIAL NBR: (\S{6})', flags=re.S)

ignoreList = {'EQUIPMENT','ELECTRONICS'}

AirtableAPIHeaders = {
    "Authorization":str("Bearer "+api_key),
    "User-Agent":"Python Script",
    "Content-Type":"application/json"
}


def checkFolder():
    filesInFolder = []
    for filename in os.listdir(pdfFolderLocation):
        if str(filename)[-3:] == 'pdf':
            filesInFolder.append(filename)
    return filesInFolder


def startPDFProcessing(filename, **kwargs):
    fileText = getPDFText(filename)
    filetype = determineFileType(fileText, filename, **kwargs)  #remove filename
    LocationAndName = [pdfFolderLocation+str(filename), filename]

    if filetype == "Mack-Update" or filetype == "Volvo-Update" or filetype == "Mack" or filetype == "Volvo":
        FieldEntries, LocationAndName, sendType = createFieldEntries(fileText, filetype, filename, **kwargs)
        return FieldEntries, LocationAndName, sendType
    
    elif filetype == "Multiple":        # if it has multiple, it will split them and make them wait for the next processing cycle
        # splitPDF(filename, fileText, filetype) 
        print("Found multiple documents combined into one.")
    
    if filetype == "Unknown" or 'debug' in kwargs or debug == True:
        try:
            writefile(fileText, pdfFolderLocation+"Debug\\", filename[:-4]+", filetype "+filetype+" (debug pdftotext).txt")  # write to errored folder if not matched
        except PermissionError:
            print("Permission error.")
        except FileExistsError:
            print("File exists.")
    

def getPDFText(filename):
    try:
        fileText = subprocess.run([pdftotextExecutable, '-nopgbrk', '-simple', '-raw', '-marginb','40', pdfFolderLocation+str(filename),'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
    except:
        return "Error"
    return fileText


def determineFileType(fileText, filename, **kwargs):        #remove filename
    line1 = fileText.split('\n', 1)[0]                 # first line of .txt file
    line2 = fileText.split('\n', 2)[1]                 # second line of .txt file
    if "Welcome to Volvo" in line1:
        filetype = "Volvo"
    elif "GSO:" in line2:
        filetype = "Mack"
    elif "MACK TRUCKS, INC." in line1:
        filetype = "Mack-Update"
    elif "PAGE  1" in line1 or "PAGE 1" in line1:
        filetype = "Volvo-Update"
    else:
        print("Unknown format.")
        filetype = "Unknown"

    if containsMultipleInvoices(filetype, fileText) == True:
        splitPDF(filename, fileText, filetype) # needs to be removed, uncomment and make work in the above function
        filetype = "Multiple"


    return filetype

def splitPDF(filename, fileText, filetype):
    pageGroups = []
    orderNumbers = []
    if filetype == "Mack-Update":
        y = 0
        allmatches = re.findall(r'(?:(Invoice Date)|(Date Printed:)|(Order Number).*?(\d{8}))', fileText, flags=re.S)
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

    elif filetype == "Volvo-Update":
        y = 1
        allmatches = re.findall(r'PAGE {,2}(\d+)', fileText, flags=re.S)
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
        volvmatches = re.findall(r'PAGE {,2}2.*?SERIAL NBR: (\S{6})', fileText, flags=re.S)
        for x in volvmatches:
            orderNumbers.append(x)

    pageCounter = 0
    pageGroupNum = 0
    moveToFolder([[pdfFolderLocation+filename, filename]],"Unsplit TRKINV")
    readOldFile = PDFReader(pdfFolderLocation+'Unsplit TRKINV\\'+filename)
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



def containsMultipleInvoices(filetype, fileText):
    if filetype == "Mack-Update":
        if len(re.findall(r'Order Number', fileText)) > 1: # if it contains Order Number more than once, it probably contains multiple documents
            return True
    elif filetype == "Volvo-Update":
        if len(re.findall(r'PAGE {,2}3', fileText)) > 1: # if it contains more than one Page 3, it's probably multiple documents combined
            return True
    return False



def writefile(string, filepath, extension):                 # write file for debugging
    a = open(filepath+extension, 'w')
    a.write(str(string))
    a.close()


def createFieldEntries(file, filetype, filename, **kwargs): #       Takes the file and processes it to take out the relevant information
    fieldEntries = {}                                       #   according to which vendor it came from, then returns the fields for
    fields = [{"fields":fieldEntries}]                      #   further formatting, to be uploaded using the Airtable API
    sendType = "Post"

    if filetype == "Mack":
        mackRegexMatches = re.findall(mackRegex, file)
        mackSpecificInfo = re.findall(mackSpecificInfoRegex, file)
        if 'debug' in kwargs:
            writefile(mackRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        for n, x in enumerate(mackSpecificInfo[0]):
            if mackUniqueInfoList[n] in headerConversionList:
                fieldEntries[headerConversionList[mackUniqueInfoList[n]][0]] = x
        for x in mackRegexMatches:
            if x[0] in headerConversionList and x[1] not in ignoreList:
                fieldEntries.update(runRegExMatching(x, headerConversionList))
        fieldEntries["Make"] = "Mack"
        fieldEntries["Status"] = "O"

    elif filetype == "Volvo":
        volvoRegexMatches = re.findall(volvoRegex, file)
        if 'debug' in kwargs:
            writefile(volvoRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        for x in volvoRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(runRegExMatching(x, headerConversionList))
        fieldEntries["Make"] = "Volvo"
        fieldEntries["Status"] = "O"
        if re.search(r'\d{6}', filename) != None:
            fieldEntries["Order Number"] = re.search(r'\d{6}', filename).group(0)

    elif filetype == "Mack-Update":
        mackUpdateRegexMatches = re.findall(mackUpdateSpecificInfoRegex, file)
        mackRegexMatches = re.findall(mackInvoiceRegex, file)
        sendType = "Update"
        if 'debug' in kwargs:
            writefile(mackUpdateRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        for x in mackUpdateRegexMatches:
            # print(x)
            id = getRecordID(x[1])
            details = {"Full VIN":x[2], "Status":"A", "Order Number":x[1]}
            fieldEntries.update(details)
            if id != None:
                fields[0].update({"id":id})
            else:
                appendToDebugLog("Order Number not found in Airtable. Creating new entry.", orderNumber=x[1], extra='Dealer code - '+x[0]+', VIN - '+x[2])
                sendType = "Post"
            if x[0] in dealerCodes:
                loc = dealerCodes[x[0]]
                fieldEntries.update({"Dealer Code":x[0], "Location":loc})
            else:
                appendToDebugLog("Location not found", orderNumber=x[1], extra='Dealer code - '+x[0])
        for x in mackRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(runRegExMatching(x, headerConversionList))
    
    elif filetype == "Volvo-Update":
        volvoUpdateRegexMatches = re.findall(volvoUpdateSpecificInfoRegex, file)
        volvoRegexMatches = re.findall(volvoInvoiceRegex, file)
        sendType = "Update"
        if 'debug' in kwargs:
            writefile(volvoUpdateRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        for x in volvoUpdateRegexMatches:
            # print(x)
            id = getRecordID(x[2])
            details = {"Full VIN":x[1], "Status":"A", "Order Number":x[2]}
            fieldEntries.update(details)
            if id != None:
                fields[0].update({"id":id})
            else:
                appendToDebugLog("Order Number not found in Airtable. Creating new entry.", orderNumber=x[2], extra='Dealer code - '+x[0]+', VIN - '+x[1])
                sendType = "Post"
            if x[0] in dealerCodes:
                loc = dealerCodes[x[0]]
                fieldEntries.update({"Dealer Code":x[0], "Location":loc})
            else:
                appendToDebugLog("Location not found", orderNumber=x[2], extra='Dealer code - '+x[0]) 
        for x in volvoRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(runRegExMatching(x, headerConversionList))
    OrderOrInvoice = ''
    if filetype == "Mack" or filetype == "Volvo":
        OrderOrInvoice = "Order - "
    elif filetype == "Mack-Update" or filetype == "Volvo-Update":
        OrderOrInvoice = "Invoice - "
    newName = OrderOrInvoice+fieldEntries['Order Number']+'.pdf'
    moveToFolder([[pdfFolderLocation+filename, newName]], '')
    LocationAndName = [pdfFolderLocation+newName, newName]

    return fields, LocationAndName, sendType


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
        print("Success\n")
        return "Successful"
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
            os.rename(x[0], pdfFolderLocation+folder+"\\Already Exists\\"+x[1][:-4]+" (1)"+x[1][-4:])
            pass
        except FileNotFoundError:
            print(x[1]+" not found.")
            pass


def main(pool, files, **kwargs):
        start_time = time.time()
        recordsToPost = []
        recordsToUpdate = []
        PostFilesToMoveToDone = []
        UpdateFilesToMoveToDone = []
        remainingFiles = set()
        remainingFiles.update(files)
        threads = pool.imap_unordered(startPDFProcessing, files)

        if threads != None:
            for thread in threads:
                if thread != None:
                    if thread[2] == "Post":
                        for y in thread[0]:
                            recordsToPost.append(y)
                        PostFilesToMoveToDone.append(thread[1])
                    elif thread[2] == "Update":
                        if len(thread[0]) > 0:
                            for y in thread[0]:
                                recordsToUpdate.append(y)
                        UpdateFilesToMoveToDone.append(thread[1])
            
        
        print("Compute time: ",time.time()-start_time)
        recordPostStatus = "Unupdated"
        recordUpdateStatus = "Unupdated"

        if len(recordsToPost) > 0:
            for y in range(0, (len(recordsToPost) // 10)+1):
                z = min(10, len(recordsToPost))
                recToPost = recordsToPost[:z]
                sendData = uploadDataToAirtable({"records":recToPost}, "Post")
                if sendData == "Successful":
                    filesToMove = set()
                    recordPostStatus = "Success"
                    print('PostFilesToMoveToDone: '+str(PostFilesToMoveToDone))
                    for x in recToPost:
                        filesToMove.add(x['fields']['Order Number'])
                    for x in PostFilesToMoveToDone:
                        if re.search(r'\d+',x[1]).group(0) in filesToMove:
                            moveToFolder([x], "Done")
                            if x[1] in remainingFiles:
                                remainingFiles.discard(x[1])
                            print("moved file, x = "+str(x[1]))
                else:
                    print("Send unsuccessful.")
                    iterations = kwargs['iterations']+1
                    recordPostStatus="Failed"
                    if len(files) == 1 or kwargs['iterations'] > 1:
                        appendToDebugLog("Send unsuccessful.", extra=sendData)
                        startPDFProcessing(files[0], debug=True)
                        moveToFolder([[pdfFolderLocation+files[0], files[0]]], "Errored")
                    else:
                        for x in remainingFiles:
                            main(pool, [x], iterations=kwargs['iterations']+1)
                time.sleep(.5)
                del recordsToPost[:z]

        content2 = {"records":recordsToUpdate}
        if len(recordsToUpdate) > 0:
            for y in range(0, (len(recordsToUpdate) // 10)+1):
                z = min(10, len(recordsToUpdate))
                recToUpdate = recordsToUpdate[:z]
                sendData2 = uploadDataToAirtable(content2, "Update")
                if sendData2 == "Successful":
                    filesToMove = set()
                    recordUpdateStatus = "Success"
                    for x in recToUpdate:
                        filesToMove.add(x['fields']['Order Number'])
                    for b in UpdateFilesToMoveToDone:
                        if re.search(r'\d+',b[1]).group(0) in filesToMove:
                            moveToFolder([b], "Done")
                            if b[1] in remainingFiles:
                                remainingFiles.discard(b[1])
                else:
                    recordUpdateStatus="Failed"
                    if len(files) == 1:
                        appendToDebugLog("Send unsuccessful.", extra=sendData2)
                        startPDFProcessing(files[0], debug=True)
                        moveToFolder([[pdfFolderLocation+files[0], files[0]]], "Errored")
                    else:
                        for x in remainingFiles:
                            main(pool, [x], iterations=kwargs['iterations']+1)
                            
                    time.sleep(.5)
                del recordsToUpdate[:z]

            if recordUpdateStatus == "Unupdated" and recordPostStatus == "Unupdated":
                for a in remainingFiles:
                    if not "TRKINV" in a:
                        moveToFolder([[pdfFolderLocation+a, a]], "Errored")
                    else:
                        moveToFolder([[pdfFolderLocation+a, a]], "Unsplit TRKINV")

            #return done, failed

                    

if __name__ == "__main__":
    p = multiprocessing.Pool()
    updateAirtableRecordsCache()
    x = 0
    while True:
        x += 1
        ListOfFiles = checkFolder()
        if len(ListOfFiles) > 0:
            main(p, ListOfFiles, iterations=0)
            #done, failed = main()
            #for x in done, writetofile(x, "Done")
            #for x in failed, etc
        else:
            print("No files found.")
        time.sleep(10)
        
        if x > 4800:      #every 12 hours #switch to time.time() last updated
            updateAirtableRecordsCache()
            x = 0
