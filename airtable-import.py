"""
    Notes!
    
"""

import re, os.path, subprocess, time
import json, requests

debug = True
sendairtabletestdata = False

mainFolder = 'C:\\airtabletest\\'

with open(mainFolder+'api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open(mainFolder+'url.txt', 'r') as url:         #   location of .txt file containing URL for the table in Airtable 
    url = url.read()                                        #   (found in api.airtable.com, not the same as the URL you see when browsing)

pdfFolderLocation = mainFolder+'python-test\\'       # location of .pdf files
pdftotextExecutable = mainFolder+'pdftotext'         # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)
filesToMoveToDone = []                                      # list storing locations of files that will be moved to the Done folder, if Airtable upload was successful
mackRegex = re.compile(r'^(?:   \S{6} {2,6}| {3,5})(?: |(.{2,32})(?<! ) +(.*)\n)', flags=re.M)
mackSpecificInfoRegex = re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n.*?Model Year:(\w+)', flags=re.S) # pulls info that doesn't follow the main pattern
mackUniqueInfoList = ['Model','GSO','Chassis Number','Model Year']
volvoRegex = re.compile(r'^ {3,6}(\S{3})\S{3} +. +. +(.*?)(:?  |\d\.\d\n)', flags=re.M)
volvolist = []

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
    #
    #   Valid entry examples:   'T-MODEL':['Model'],
    #                           'TRUCK MODEL':['Model',r'\d'],
    #                           'MODEL':['Model',]
    #                           'ENGINE':['Engine Make',r'^.*? (\w+)','Engine Model',r'^(\S*)']

    #   That last example converts this:    MP7-425M MACK 425HP @ 1500-180
    #   To this:                            {'Engine Make': 'MACK', 'Engine Model': 'MP7-425M'}

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


def main():
#    try:
        records = []
        content = {"records":records}
        for filename in os.listdir(pdfFolderLocation):
            if str(filename)[-3:] == 'pdf':    #   if filename is a PDF
                subprocess.run([pdftotextExecutable, '-nopgbrk', '-simple', '-raw', '-marginb','40', pdfFolderLocation+str(filename)]) # convert pdf to text
                pdfFile = str(pdfFolderLocation+str(filename))           # create string of filepath to .pdf file
                txtFile = pdfFile[:-3]+'txt'
                filetype = "None"
                print(txtFile)
                while os.path.exists(txtFile) != True:
                    time.sleep(5)
                    print("Waiting for file creation")

                with open(txtFile, 'r+') as c:
                    n = c.read()
                line1 = n.split('\n', 1)[0]                 # first line of .txt file
                line2 = n.split('\n', 2)[1]                 # second line of .txt file
                if "Welcome to Volvo" in line1:
                    filetype = "Volvo"
                elif "GSO:" in line2:
                    filetype = "Mack"
                else:
                    print("Unknown format")
                    filetype = "None"
                    x = 20
                    while x > 0:
                        try:
                            os.rename(txtFile, pdfFolderLocation+"\\Errored\\"+filename[:-4]+" unknown format.txt")  # move to errored folder if not matched
                            break
                        except PermissionError:
                            time.sleep(3)
                            print("Permission error. Trying {x} more time(s)") 
                            x -= 1
                        except FileExistsError:
                            print("File exists")
                            break

                if filetype != "None":
                    print(filetype)
                    if debug == True:                   # create a regex debug file
                        writefile(n, txtFile[:-4], " (debug-pdftotext).txt")
                    else:                               # if not debugging, move pdfs to Done folder
                        filesToMoveToDone.append([pdfFile, filename])
                    records.append(dataimport(n, filetype, filename))
                    os.remove(txtFile)

                print(filename)
        print(content)
        uploadDataToAirtable(content)
 #   except:
 #       print("something went wrong")


def writefile(n, filepath, extension):                      # write file for debugging
    a = open(filepath+extension, 'w')
    a.write(str(n))
    a.close()


def dataimport(file, filetype, filename):                             #   takes the file and processes it to take out the relevant information
    # time.sleep(.4)                                          #   according to which vendor it came from, then returns the fields for
    print(f"Importing {filetype} info")                     #   further formatting, to be uploaded using the Airtable API

    fieldEntries = {}
    fields = {"fields":fieldEntries}
    if filetype == "Mack":
#        reg = re.compile(r'.*?Year:(\w*).*?MODEL\) (.*?)\n.*?ENGINE PACKAGE (.*?)\n.*?TRANSMISSION (.*?)\n.*?FRONT AXLE.*?AXLE.*?AXLE (.*?)\n.*?REAR AXLES - TANDEM (.*?)\n.*?REAR AXLE RATIO RATIO (\d\.\d\d).*?SUSPENSION - TANDEM (.*?)\n.*?DIFFERENTIAL (.*?)\n.*?WHEELBASE (.*?)\n.*?FUEL TANK - LH (.*?)\n.*?FIFTH WHEEL (.*?)\n.*?SLEEPER BOX (.*?)\n.*?DOOR OPENING OPTIONS (.*?)\n.*?MIRRORS - EXTERIOR (.*?)\n.*?REFRIGERATOR (.*?)\n.*?INVERTER - POWER (.*?)\n.*?TIRES BRAND/TYPE - FRONT (.*?)\n.*?WHEELS - FRONT (.*?)\n.*?TIRES BRAND/TYPE - REAR (.*?)\n.*?WHEELS - REAR (.*?)\n.*?PAINT COLOR - AREA A (.*?)\n.*?PRICE BOOK\nLEVEL:\n(.*?)\n',g,s,)
        mackRegexMatches = re.findall(mackRegex, file)
        mackSpecificInfo = re.findall(mackSpecificInfoRegex, file)
        if debug == True:
            writefile(mackRegexMatches, pdfFolderLocation+filename+" (debug-regexmatches)",".txt")
        for n, x in enumerate(mackSpecificInfo[0]):
            if mackUniqueInfoList[n] in headerConversionList:
                fieldEntries[headerConversionList[mackUniqueInfoList[n]][0]] = x
        for x in mackRegexMatches:
            if x[0] in headerConversionList and x[1] not in ignoreList:
                fieldEntries.update(prepforupload(x))
        fieldEntries["Make"] = "Mack"
        fieldEntries["Status"] = "O"
    elif filetype == "Volvo":
        volvoRegexMatches = re.findall(volvoRegex, file)
        if debug == True:
            writefile(volvoRegexMatches, pdfFolderLocation+filename+" (debug-regexmatches)",".txt")
        for x in volvoRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(prepforupload(x))
        fieldEntries["Make"] = "Volvo"
        fieldEntries["Status"] = "O"
        if re.search(r'\d{6}', filename) != None:
            fieldEntries["Order Number"] = re.search(r'\d{6}', filename).group(0)
    return fields


def prepforupload(content):
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

    # print(preppedData)
    return preppedData


def uploadDataToAirtable(content):                                # uploads the data to Airtable
    headers = {
        "Authorization":str("Bearer "+api_key),
        "User-Agent":"Python Script",
        "Content-Type":"application/json"
    }
    x = requests.post(url,data=None,json=content,headers=headers)
    print("\n\nPost response: ",x.json())
    print("\n Post HTTP code:", x)
    if x == "<Response [200]>":                                 # if Airtable upload successful, move PDF files to Done folder
        for y in filesToMoveToDone:
            os.rename(y[0], pdfFolderLocation+"\\Done\\"+y[1])

if debug == True and sendairtabletestdata == True:
    testdata={
        "records": [
            {
                "fields": {
                    "Name":"TULtest",
                    "Status":"Does Not Exist"
                }
            },
            {
                "fields": {
                    "Name":"TULtest2",
                    "Status":"Does Not Exist"
                }
            }
        ]
    }
    uploadDataToAirtable(testdata)
else:
    main()
