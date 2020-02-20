"""
    Notes!
    
"""

import re, os.path, subprocess, time
import json, requests

debug = True
sendairtabletestdata = False

with open('C:\\airtabletest\\api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open('C:\\airtabletest\\url.txt', 'r') as url:         #   location of .txt file containing URL for the table in Airtable 
    url = url.read()                                        #   (found in api.airtable.com, not the same as the URL you see when browsing)

pdfFolderLocation = 'C:\\airtabletest\\python-test\\'       # location of .pdf files
pdftotextExecutable = 'C:\\airtabletest\\pdftotext'         # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)
filesToMoveToDone = []                                      # list storing locations of files that will be moved to the Done folder, if Airtable upload was successful
mackRegex = re.compile(r'^(?:\S{6} {2,}|)(.{2,32})(?<! ) +(.*)\n', flags=re.M)
mackSpecificInfoRegex = re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n\n.*?Model Year:(\w+)', flags=re.S) # pulls info that doesn't follow the main pattern
mackUniqueInfoList = ['Model','GSO','Chassis Number','Model Year']
volvoRegex = re.compile(r'')
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
    'TIRES BRAND/TYPE - FRONT':['FF Tire Size',r'^.*?(\d\dR.*?) '],
    'SLEEPER BOX':['Sleeper'],
    'PAINT COLOR - AREA A':['Color'],
    'PAINT COLOR - FIRST COLOR':['Color']
    
}


def main():
#    try:
        records = []
        content = {"records":records}
        for filename in os.listdir(pdfFolderLocation):
            if str(filename)[-3:] != 'txt' and str(filename)[-4] == '.':    #   if filename doesn't contain 'txt' at the end
                                                                            #   and is a file, not a folder, then:
                subprocess.run([pdftotextExecutable, '-nopgbrk', '-table', '-marginb','40', pdfFolderLocation+str(filename)]) # convert pdf to text
                filepath = pdfFolderLocation+str(filename)[:-4]           # create string of filepath to .txt file
                filetype = "None"
                print(filepath)
                while os.path.exists(filepath+".txt") != True:
                    time.sleep(5)
                    print("Waiting for file creation")

                with open(filepath+'.txt', 'r+') as c:
                    n = c.read()
                line1 = n.split('\n', 1)[0]                 # first line of .txt file
                line2 = n.split('\n', 3)[2]                 # second line of .txt file
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
                            os.rename(filepath+".txt", pdfFolderLocation+"\\Errored\\"+filename[:-4]+" unknown format.txt")  # move to errored folder if not matched
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
                        writefile(n, filepath, " (debug).txt")
                    else:                               # if not debugging, move pdfs to Done folder
                        filesToMoveToDone.append([filepath+'.pdf', filename])
                    records.append(dataimport(n, filetype, filename))
                    os.remove(filepath+'.txt')

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
            writefile(mackRegexMatches,"C:\\airtabletest\\python-test\\"+filename+" (regexmatches)",".txt")
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
            writefile(volvoRegexMatches,"C:\\airtabletest\\volvoRegexmatches.txt","")
            print(volvoRegexMatches)
        # for x in volvoRegexMatches:
        #     if x[0] in volvolist:
        #         fieldEntries.update(prepforupload(x))
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
