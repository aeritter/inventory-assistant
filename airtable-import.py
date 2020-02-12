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

filefolder = 'C:\\airtabletest\\python-test\\'              # location of .pdf files
pdftotextlocation = 'C:\\airtabletest\\pdftotext'           # location of pdftotext.exe (obtained from xpdfreader.com commandline tools)
Mackregex = re.compile(r'^(.+?) {2,}(.*)\n', flags=re.M)
Volvoregex = re.compile(r'')


def checkfornewfiles():
#    try:
        for filename in os.listdir(filefolder):
            if str(filename)[-3:] != 'txt' and str(filename)[-4] == '.':    #   if filename doesn't contain 'txt' at the end
                                                                            #   and is a file, not a folder, then:
                subprocess.run([pdftotextlocation, '-nopgbrk', '-table','-margint', '70', '-marginb','40', filefolder+str(filename)]) # convert pdf to text
                filepath = filefolder+str(filename)[:-4]           # create string of filepath to .txt file
                filetype = "None"
                print(filepath)
                while os.path.exists(filepath+".txt") != True:
                    time.sleep(5)
                    print("Waiting for file creation")

                with open(filepath+'.txt', 'r+') as c:
                    n = c.read()
                line1 = n.split('\n', 1)[0]                 # first line of .txt file
                # line2 = n.split('\n', 2)[1]                 # second line of .txt file
                if "Selected & Major" in line1:
                    filetype = "Volvo"
                elif "Model Year:" in line1:
                    filetype = "Mack"
                else:
                    print("Unknown format")
                    filetype = "None"
                    x = 20
                    while x > 0:
                        try:
                            os.rename(filepath+".txt", filefolder+"\\Errored\\"+filename[:-4]+" unknown format.txt")  # move to errored folder if not matched
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
                        os.rename(filepath+'.pdf', filefolder+"\\Done\\"+filename)
                    dataimport(n, filetype)
                    os.remove(filepath+'.txt')

                print(filename)
 #   except:
 #       print("something went wrong")


def writefile(n, filepath, extension):                                 # write file for debugging
    a = open(filepath+extension, 'w')
    a.write(str(n))
    a.close()

def dataimport(file, filetype):                             #   takes the file and processes it to take out the relevant information
    time.sleep(.4)                                           #   according to which vendor it came from, then returns a list of dictionaries
    print(f"Importing {filetype} info")                     #   to be uploaded to Airtable

    content = []                                            # list of dictionaries, one dictionary per airtable row
    if filetype == "Mack":
#        reg = re.compile(r'.*?Year:(\w*).*?MODEL\) (.*?)\n.*?ENGINE PACKAGE (.*?)\n.*?TRANSMISSION (.*?)\n.*?FRONT AXLE.*?AXLE.*?AXLE (.*?)\n.*?REAR AXLES - TANDEM (.*?)\n.*?REAR AXLE RATIO RATIO (\d\.\d\d).*?SUSPENSION - TANDEM (.*?)\n.*?DIFFERENTIAL (.*?)\n.*?WHEELBASE (.*?)\n.*?FUEL TANK - LH (.*?)\n.*?FIFTH WHEEL (.*?)\n.*?SLEEPER BOX (.*?)\n.*?DOOR OPENING OPTIONS (.*?)\n.*?MIRRORS - EXTERIOR (.*?)\n.*?REFRIGERATOR (.*?)\n.*?INVERTER - POWER (.*?)\n.*?TIRES BRAND/TYPE - FRONT (.*?)\n.*?WHEELS - FRONT (.*?)\n.*?TIRES BRAND/TYPE - REAR (.*?)\n.*?WHEELS - REAR (.*?)\n.*?PAINT COLOR - AREA A (.*?)\n.*?PRICE BOOK\nLEVEL:\n(.*?)\n',g,s,)
        mackRegexMatches = re.findall(Mackregex, file)
        writefile(mackRegexMatches,"C:\\airtabletest\\test.txt","")
        print(mackRegexMatches)
    elif filetype == "Volvo":
        print()

    # pattern = reg.search(file)

    return content
    

def posttoairtable(content):                                # uploads the data to Airtable
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
    posttoairtable(testdata)
else:
    checkfornewfiles()                      # main
