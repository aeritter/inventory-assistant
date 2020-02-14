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

pdfFolderLocation = 'C:\\airtabletest\\python-test\\'              # location of .pdf files
pdftotextExecutable = 'C:\\airtabletest\\pdftotext'           # location of pdftotext.exe file (obtained from xpdfreader.com commandline tools)
mackRegex = re.compile(r'^(.+?) {2,}(.*)\n', flags=re.M)
mackSpecificInfoRegex = re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Chassis:(.*?)\n\n.*?Model Year:(\w+)', flags=re.S)
volvoRegex = re.compile(r'')
mackUniqueInfoList = ['Model','GSO','Chassis Number','Model Year']
macklist = ['CHASSIS (BASE MODEL)']
volvolist = []
    # dictionary containing headers pulled from file and their respective values in Airtable
headerConversionList = {
    'Model':'Model',                        'GSO':'Order Number',
    # 'Chassis Number':'Chassis Number',
    'Model Year':'Year',                    
    # 'CHASSIS (BASE MODEL)':'Chassis',
           'TRANSMISSION':'Trans Model',
    'FRONT AXLE':'Front Axle',              'REAR AXLES - TANDEM':'Rear Axle',
    'REAR AXLE RATIO':'Ratio',              'WHEELBASE':'Wheelbase',
    'SLEEPER BOX':'Sleeper',                'PAINT COLOR - AREA A':'Color',
    'PAINT COLOR - FIRST COLOR':'Color'
    
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
                        os.rename(filepath+'.pdf', pdfFolderLocation+"\\Done\\"+filename)
                    records.append(dataimport(n, filetype))
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

def dataimport(file, filetype):                             #   takes the file and processes it to take out the relevant information
    time.sleep(.4)                                          #   according to which vendor it came from, then returns the fields for
    print(f"Importing {filetype} info")                     #   further formatting, to be uploaded using the Airtable API

    fieldEntries = {}
    fields = {"fields":fieldEntries}
    if filetype == "Mack":
#        reg = re.compile(r'.*?Year:(\w*).*?MODEL\) (.*?)\n.*?ENGINE PACKAGE (.*?)\n.*?TRANSMISSION (.*?)\n.*?FRONT AXLE.*?AXLE.*?AXLE (.*?)\n.*?REAR AXLES - TANDEM (.*?)\n.*?REAR AXLE RATIO RATIO (\d\.\d\d).*?SUSPENSION - TANDEM (.*?)\n.*?DIFFERENTIAL (.*?)\n.*?WHEELBASE (.*?)\n.*?FUEL TANK - LH (.*?)\n.*?FIFTH WHEEL (.*?)\n.*?SLEEPER BOX (.*?)\n.*?DOOR OPENING OPTIONS (.*?)\n.*?MIRRORS - EXTERIOR (.*?)\n.*?REFRIGERATOR (.*?)\n.*?INVERTER - POWER (.*?)\n.*?TIRES BRAND/TYPE - FRONT (.*?)\n.*?WHEELS - FRONT (.*?)\n.*?TIRES BRAND/TYPE - REAR (.*?)\n.*?WHEELS - REAR (.*?)\n.*?PAINT COLOR - AREA A (.*?)\n.*?PRICE BOOK\nLEVEL:\n(.*?)\n',g,s,)
        mackRegexMatches = re.findall(mackRegex, file)
        mackSpecificInfo = re.findall(mackSpecificInfoRegex, file)
        if debug == True:
            writefile(mackRegexMatches,"C:\\airtabletest\\mackRegexmatches.txt","")
        for n, x in enumerate(mackSpecificInfo[0]):
            if mackUniqueInfoList[n] in headerConversionList:
                fieldEntries[headerConversionList[mackUniqueInfoList[n]]] = x
        for x in mackRegexMatches:
            if x[0] in headerConversionList:
                fieldEntries.update(prepforupload(x))
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
    columnheader = headerConversionList[content[0]]
    contentasjson = {columnheader:content[1]}
    # if debug == True:
    #     print(contentasjson)
    return contentasjson

def uploadDataToAirtable(content):                                # uploads the data to Airtable
    headers = {
        "Authorization":str("Bearer "+api_key),
        "User-Agent":"Python Script",
        "Content-Type":"application/json"
    }
    x = requests.post(url,data=None,json=content,headers=headers)
    print("Post response: ",x.json())
    print("\n Post HTTP code:", x)

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
