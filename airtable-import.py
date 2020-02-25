import re, os.path, subprocess, time
import json, requests, multiprocessing

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

mackUpdateRegex = re.compile(r'Order Number.*?(\S{4,5}) +(\d{8}).*?VIN #.*?(\S{17}) ', flags=re.S)
volvoUpdateRegex = re.compile(r'DEALER\..*?(\S{5}) +.*?NBR:.*?(\S{17}).*? SERIAL NBR: (\S{6})', flags=re.S)

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
#    try:
        fileText = subprocess.run([pdftotextExecutable, '-nopgbrk', '-simple', '-raw', '-marginb','40', pdfFolderLocation+str(filename),'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
        filetype = "None"

        line1 = fileText.split('\n', 1)[0]                 # first line of .txt file
        line2 = fileText.split('\n', 2)[1]                 # second line of .txt file
        if "Welcome to Volvo" in line1:
            filetype = "Volvo"
        elif "GSO:" in line2:
            filetype = "Mack"
        elif "MACK TRUCKS, INC." in line1:
            filetype = "Mack-Update"
        elif "PAGE  1" in line1:
            filetype = "Volvo-Update"
        else:
            print("Unknown format.")
            try:
                writefile(fileText, pdfFolderLocation+"Debug\\", filename[:-4]+" unknown format.txt")  # write to errored folder if not matched
            except PermissionError:
                print("Permission error.")
            except FileExistsError:
                print("File exists.")

        LocationAndName = [pdfFolderLocation+str(filename), filename]
        if filetype == "Mack" or filetype == "Volvo":
            if 'debug' in kwargs:                   # create a regex debug file
                writefile(fileText, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-pdftotext).txt")
            return createFieldEntries(fileText, filetype, filename, **kwargs), LocationAndName, "Post"

        elif filetype == "Mack-Update" or filetype == "Volvo-Update":

            return createFieldEntries(fileText, filetype, filename, **kwargs), LocationAndName, "Update"

#    except:
#        print("something went wrong.")


def writefile(string, filepath, extension):                 # write file for debugging
    a = open(filepath+extension, 'w')
    a.write(str(string))
    a.close()


def createFieldEntries(file, filetype, filename, **kwargs): #       Takes the file and processes it to take out the relevant information
    fieldEntries = {}                                       #   according to which vendor it came from, then returns the fields for
    fields = [{"fields":fieldEntries}]                      #   further formatting, to be uploaded using the Airtable API

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
        mackUpdateRegexMatches = re.findall(mackUpdateRegex, file)
        if 'debug' in kwargs:
            writefile(mackUpdateRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        fields = []
        for x in mackUpdateRegexMatches:
            print(x)
            if x[0] in dealerCodes:
                loc = dealerCodes[x[0]]
                id = getRecordID(x[1])
                details = {"Full VIN":x[2], "Status":"A", "Location":loc, "Dealer Code":x[0]}
                if id != None:
                    fields.append({"id":id, "fields":details})
                else:
                    appendToDebugLog("Order Number not found in ORDERED UNITS list view", orderNumber=x[1], extra='Dealer code - '+x[0]+', VIN - '+x[2])
            else:
                appendToDebugLog("Location not found", orderNumber=x[1], extra='Dealer code - '+x[0])
    
    elif filetype == "Volvo-Update":
        volvoUpdateRegexMatches = re.findall(volvoUpdateRegex, file)
        if 'debug' in kwargs:
            writefile(volvoUpdateRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        fields = []
        for x in volvoUpdateRegexMatches:
            print(x)
            if x[0] in dealerCodes:
                loc = dealerCodes[x[0]]
                id = getRecordID(x[2])
                details = {"Full VIN":x[1], "Status":"A", "Location":loc, "Dealer Code":x[0]}
                if id != None:
                    fields.append({"id":id, "fields":details})
                else:
                    appendToDebugLog("Order Number not found in ORDERED UNITS list view", orderNumber=x[2], extra='Dealer code - '+x[0]+', VIN - '+x[1])
            else:
                appendToDebugLog("Location not found", orderNumber=x[2], extra='Dealer code - '+x[0])        

    return fields


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
    print("\n\nPost response: ",x.json())
    print("\nPost HTTP code:", x.status_code)
    if x.status_code == 200:                                 # if Airtable upload successful, move PDF files to Done folder
        print("Success\n")
        return "Successful"
    else:
        return {'content':content, 'failureText':x.text}

def retrieveRecordsFromAirtable():
    x = requests.get(url+"?fields%5B%5D=Order+Number&fields%5B%5D=Status&view=ORDERED+UNITS", data=None, headers=AirtableAPIHeaders)
    return x.json()['records']

def updateAirtableRecordsCache():
    ListOfAirtableRecords = str(retrieveRecordsFromAirtable()).replace("\'","\"") # pull records, convert to str, replace single quotes with double to make json format valid
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
        a.write(str(time.ctime()+", Order #: "+orderNumber+", Error: "+errormsg+', Extra information: '+extra+'\n'))
        a.close()
    except:
        print("Can't append to debug log file.")


def moveToFolder(filesToMove, folder):      # format: moveToFolder([["C:\\Path\\To\\File.pdf", "File.pdf"]["C:\\etc\\etc.etc", "etc.etc"]], "Errored")
    for x in filesToMove:
        try:
            os.rename(x[0], pdfFolderLocation+folder+"\\"+x[1])
        except FileExistsError:
            print("File", x[1], "exists in", folder, "folder.")
            os.rename(x[0], pdfFolderLocation+folder+"\\Already Exists\\"+x[1][:-4]+" (1)"+x[1][-4:])


def main(pool, files):
        start_time = time.time()
        recordsToPost = []
        recordsToUpdate = []
        filesToMoveToDone = []
        threads = pool.imap_unordered(startPDFProcessing, files)

        for x in threads:
            if x != None:
                if x[2] == "Post":
                    for y in x[0]:
                        recordsToPost.append(y)
                elif x[2] == "Update":
                    if len(x[0]) > 0:
                        for y in x[0]:
                            recordsToUpdate.append(y)
                filesToMoveToDone.append(x[1])
            
        
        print("Compute time: ",time.time()-start_time)

        content = {"records":recordsToPost}
        if len(recordsToPost) > 0:
            sendData = uploadDataToAirtable(content, "Post")
            if sendData == "Successful":
                moveToFolder(filesToMoveToDone, "Done")
            else:
                print("Send unsuccessful.")
                if len(files) == 1:
                    appendToDebugLog("Send unsuccessful.", extra=sendData)
                    startPDFProcessing(files[0], debug=True)
                    moveToFolder([[pdfFolderLocation+files[0], files[0]]], "Errored")
                else:
                    for x in files:
                        main(pool, [x])
                time.sleep(.5)

        content2 = {"records":recordsToUpdate}
        if len(recordsToUpdate) > 0:
            sendData2 = uploadDataToAirtable(content2, "Update")
            if sendData2 == "Successful":
                moveToFolder(filesToMoveToDone, "Done")
            else:
                print("Send unsuccessful.")
                if len(files) == 1:
                    appendToDebugLog("Send unsuccessful.", extra=sendData2)
                    startPDFProcessing(files[0], debug=True)
                    print(files[0])
                    moveToFolder([[pdfFolderLocation+files[0], files[0]]], "Errored")
                else:
                    for x in files:
                        main(pool, [x])
                time.sleep(.5)

        if len(recordsToPost) == 0 and len(recordsToUpdate) == 0:
            for x in files:
                moveToFolder([[pdfFolderLocation+x, x]], "Errored")

                    


if __name__ == "__main__":
    p = multiprocessing.Pool()
    updateAirtableRecordsCache()
    x = 0
    while True:
        x += 1
        ListOfFiles = checkFolder()
        if len(ListOfFiles) > 0:
            main(p, ListOfFiles)
        else:
            print("No files found.")
        time.sleep(10)
        
        if x > 30:      #every 5 minutes
            updateAirtableRecordsCache()
            x = 0
