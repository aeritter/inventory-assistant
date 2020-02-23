"""
    Notes!
    
"""

import re, os.path, subprocess, time
import json, requests, multiprocessing

mainFolder = 'C:\\airtabletest\\'

with open(mainFolder+'api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open(mainFolder+'url.txt', 'r') as url:         #      Location of .txt file containing URL for the table in Airtable 
    url = url.read()                                 #   (found in api.airtable.com, not the same as the URL you see when browsing)

pdfFolderLocation = mainFolder+'python-test\\'       # location of .pdf files
pdftotextExecutable = mainFolder+'pdftotext.exe'         # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)
mackRegex = re.compile(r'^(?:   \S{6} {2,6}| {3,5})(?: |(.{2,32})(?<! ) +(.*)\n)', flags=re.M)
mackSpecificInfoRegex = re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n.*?Model Year:(\w+)', flags=re.S) # pulls info that doesn't follow the main pattern
mackUniqueInfoList = ['Model','GSO','Chassis Number','Model Year']
volvoRegex = re.compile(r'^ {3,6}(\S{3})\S{3} +. +. +(.*?)(:?  |\d\.\d\n)', flags=re.M)

ignoreList = {'EQUIPMENT','ELECTRONICS'}

    #       Dictionary containing headers pulled from file and their respective values in Airtable
    #
    #   FORMAT:     'Name of variable identifier':['Name of column in Airtable', r'insert RegEx for variable here']
    #
    #       This is a Python dictionary, containing keys for the variable identifiers, and values which contain
    #   a list, with the first entry in the list being the matching Airtable column and the second entry in the
    #   list being the RegEx string needed to pull out the important information from the matched variable.
    #       If no extra parsing needs to be done for the variable, there is no need to place a second item in a
    #   list, but the value in the key:value pair always needs to be a list (contain brackets)
    #       A list is used instead of a dictionary because it may be necessary to have two or more lines of RegEx
    #   in order to parse all variations of a string for the same header (meaning multiple instances of the header,
    #   which cannot coexist within a dictionary).

    #   Valid entry examples:   'ENGINE':['Engine Make'],
    #                           'TRUCK MODEL':['Model',r'\d'],
    #                           'MODEL':['Model',],
    #                           'ENGINE':['Engine Make',r'^.*? (\w+)','Engine Model',r'^(\S*)'],

    #   That last example converts this:    MP7-425M MACK 425HP @ 1500-180
    #   To this:                            {'Engine Make': 'MACK', 'Engine Model': 'MP7-425M'}

    #   The first example simply copies
    #       the entire line:                MP7-425M MACK 425HP @ 1500-180
    #   Which would look like this:         {'Engine Make': 'MP7-425M MACK 425HP @ 1500-180'}
    
    #       That converted example is then added to the rest of those types of entries which are finally uploaded  
    #   to Airtable, with the first value in each set being the column header (ex. Engine Make) and the second value 
    #   being the entry under the column for that vehicle.

headerConversionList = {       
# Mack 
    'Model':['Model'],
    'GSO':['Order Number'],
    # 'Chassis Number':'Chassis Number',
    'Model Year':['Year'],
    # 'CHASSIS (BASE MODEL)':'Chassis',
    'ENGINE PACKAGE':['Engine Make',r'^.*? (\w+)', 'Engine Model',r'^(\S*)', 'HP',r'(\d{3}HP)'],
    'ENGINE PACKAGE, COMBUSTION':['Engine Make',r'^.*? (\w+)', 'Engine Model',r'^(\S*)', 'HP',r'(\d{3}HP)'],
    'TRANSMISSION':['Trans Model', '','Transmission',r'(MACK|ALLISON|EATON-FULLER)'],
    'FRONT AXLE':['Front Axle',r'\.*?(\d{5})#'],
    'REAR AXLES - TANDEM':['Rear Axle',r'\.*?(\d{5})#'],
    'REAR AXLE RATIO':['Ratio',r'\.*?(\d.\d\d)'],
    'REAR SUSPENSION - TANDEM':['Suspension',r''],
    'WHEELBASE':['Wheelbase'],
    'TIRES BRAND/TYPE - REAR':['RR Tire Size',r'^.*?(\d\dR.*?) '],
    'WHEELS - FRONT':['FF Wheels',r'(ALUM)'],
    'TIRES BRAND/TYPE - FRONT':['FF Tire Size',r'^.*?(\d\dR.*?) '],
    'WHEELS - REAR':['RR Wheels',r'(ALUM)'],
    'SLEEPER BOX':['Sleeper'],
    'PAINT COLOR - AREA A':['Color'],
    'PAINT COLOR - FIRST COLOR':['Color'],

# Volvo
    '008':['Model'],
    'A19':['Year', r'(\d*?) '],
    '2CX':['Sleeper',r'(\d.*?(?:-ROOF|ROOF)|DAY CAB)'],
    '101':['Engine Make',r'(\w*?) ', 'Engine Model',r'^.*? (\w*?) ', 'HP',r'(\d{3}HP)'],
    '270':['Trans Model','','Transmission',r'(VOLVO|ALLISON)'],
    '330':['Rear Axle',r'.*? (\d.*?)LB'],
    '350':['Suspension'],
    '370':['Front Axle',r'.*? (\d.*?)LB'],
    'TAX':['Ratio',r'(.*?) '],
    '400':['Wheelbase',r'(\d*?")'],
    '093':['FF Tire Size',r'^.*?(\d\dR.*?) '],
    '084':['FF Wheels',r'(ALUM|STEEL)'],
    '094':['RR Tire Size',r'^.*?(\d\dR.*?) '],
    '085':['RR Wheels',r'(ALUM|STEEL)'],
    '980':['Color']

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
        else:
            print("Unknown format.")
            try:
                writefile(fileText, pdfFolderLocation+"Errored\\", filename[:-4]+" unknown format.txt")  # write to errored folder if not matched
            except PermissionError:
                print("Permission error.")
            except FileExistsError:
                print("File exists.")

        if filetype != "None":
            LocationAndName = [pdfFolderLocation+str(filename), filename]

            if 'debug' in kwargs:                   # create a regex debug file
                writefile(fileText, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-pdftotext).txt")

            return createFieldEntries(fileText, filetype, filename, **kwargs), LocationAndName

#    except:
#        print("something went wrong.")


def writefile(string, filepath, extension):                 # write file for debugging
    a = open(filepath+extension, 'w')
    a.write(str(string))
    a.close()


def createFieldEntries(file, filetype, filename, **kwargs):           #       Takes the file and processes it to take out the relevant information
    fieldEntries = {}                                       #   according to which vendor it came from, then returns the fields for
    fields = {"fields":fieldEntries}                        #   further formatting, to be uploaded using the Airtable API

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
                fieldEntries.update(runRegExMatching(x))
        fieldEntries["Make"] = "Mack"
        fieldEntries["Status"] = "O"

    elif filetype == "Volvo":
        volvoRegexMatches = re.findall(volvoRegex, file)
        if 'debug' in kwargs:
            writefile(volvoRegexMatches, pdfFolderLocation+"Debug\\", filename[:-4]+" (debug-regexmatches).txt")
        for x in volvoRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(runRegExMatching(x))
        fieldEntries["Make"] = "Volvo"
        fieldEntries["Status"] = "O"
        if re.search(r'\d{6}', filename) != None:
            fieldEntries["Order Number"] = re.search(r'\d{6}', filename).group(0)

    return fields


def runRegExMatching(content):
    columnHeader = headerConversionList[content[0]]
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


def uploadDataToAirtable(content):                                # uploads the data to Airtable
    headers = {
        "Authorization":str("Bearer "+api_key),
        "User-Agent":"Python Script",
        "Content-Type":"application/json"
    }
    x = requests.post(url,data=None,json=content,headers=headers)
    print("\n\nPost response: ",x.json())
    print("\nPost HTTP code:", x.status_code)
    if x.status_code == 200:                                 # if Airtable upload successful, move PDF files to Done folder
        print("Success\n")
        return "Successful"
    else:
        return {'content':content, 'failureText':x.text}


def appendToDebugLog(content, errormsg):
    print(content)
    print(errormsg)
    try:
        a = open(pdfFolderLocation+"Debug\\Debug log.txt", "a+")
        orderNumber = ''
        try:
            if 'Order Number' in content['records'][0]['fields']:
                orderNumber = content['records'][0]['fields']['Order Number']
        except:
            print("Can't find Order Number!")
        a.write(str(time.ctime()+", Order #: "+orderNumber+", Error: "+errormsg+'\n'))
        a.close()
    except:
        print("Can't append to debug log file.")


def moveToFolder(filesToMove, folder):      # format: moveToFolder(["C:\\Path\\To\\File.pdf", "File.pdf"], "Errored")
    for x in filesToMove:
        try:
            os.rename(x[0], pdfFolderLocation+folder+"\\"+x[1])
        except FileExistsError:
            print("File", x[1], "exists in", folder, "folder.")
            os.rename(x[0], pdfFolderLocation+folder+"\\"+x[1][:-4]+" (1)"+x[1][-4:])


def main(pool, files):
        start_time = time.time()
        records = []
        filesToMoveToDone = []
        threads = pool.imap_unordered(startPDFProcessing, files)

        for x in threads:
            records.append(x[0])
            filesToMoveToDone.append(x[1])
        
        print("Compute time: ",time.time()-start_time)

        content = {"records":records}
        sendData = uploadDataToAirtable(content)

        if sendData == "Successful":
            moveToFolder(filesToMoveToDone, "Done")
            return "Success"
        else:
            print("Send unsuccessful.")
            if len(files) == 1:
                # print(sendData)
                appendToDebugLog(sendData['content'], sendData['failureText'])
                startPDFProcessing(files[0], debug=True)
                moveToFolder([[pdfFolderLocation+files[0], files[0]]], "Errored")
            else:
                for x in files:
                    main(pool, [x])
            time.sleep(.5)
                    


if __name__ == "__main__":
    p = multiprocessing.Pool()
    while True:
        ListOfFiles = checkFolder()
        if len(ListOfFiles) > 0:
            main(p, ListOfFiles)
        else:
            print("No files found.")
        time.sleep(10)
