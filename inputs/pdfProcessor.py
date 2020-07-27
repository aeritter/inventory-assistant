import subprocess, threading
import time, os, re, json, urllib, configparser
import fitz # PyMuPDF
import win32net
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
config = configparser.ConfigParser()
config.read(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+"/settings.ini")

from .inventoryObject import inventoryObject

reSearchInvoiceNum = re.compile(r'(?<= )\d{7}(?= |\n)|\d{2}/\d{5}')     #NOTE: Needs to be moved to pdfProcessingSettings.json


pdfFolderLocation = config['pdfProcessor']['pdf_folder']+"/"
if pdfFolderLocation[:2] == '//' or pdfFolderLocation[:2] == '\\\\':
    netdata = {
        'remote': config['pdfProcessor']['pdf_folder'],
        'local':'',
        'username':config['pdfProcessor']['username'],
        'domainname':config['pdfProcessor']['domain_name'],
        'password':config['pdfProcessor']['password']
    }
    try:
        win32net.NetUseAdd(None, 2, netdata)
    except:
        print("Could not connect to network share.")

DebugFolder = config['pdfProcessor']['debug_folder']
SettingsFolder = config['pdfProcessor']['settings_folder']
OriginalDocsFolder = config['pdfProcessor']['original_docs_folder']
DocumentsFolder = config['pdfProcessor']['documents_folder']
pdftotextExecutable = SettingsFolder+"/pdftotext.exe"


class PDFProcessor(object):
    def __init__(self, pool, addToInventory, addToErrorLog):
        '''
        pool = multiprocessing.Pool() in main
        addToQueue = function from input class for passing inventory object and source
        errorQueue = function from input class for errors
        '''
        self.pdfProcessingData = PDFProcessingSettingsObj(addToErrorLog)
        self.eventHandler = LogEventHandler(pool, addToInventory, addToErrorLog, self.pdfProcessingData)
        self.observer = Observer()
        self.observer.schedule(self.eventHandler, pdfFolderLocation)
        print('Watching for files.', end='\r')
        self.observer.start()
            

class LogEventHandler(PatternMatchingEventHandler):
    def __init__(self, pool, addToInventory, addToErrorLog, pdfProcessingData):
        self.pool = pool
        self.addToInventory = addToInventory
        self.addToErrorLog = addToErrorLog
        self.pdfProcessingData = pdfProcessingData
        PatternMatchingEventHandler.__init__(self, patterns=['*.pdf'], ignore_directories=True)

    def on_created(self, event):
        threading.Thread(target=(processPDF), args=(self.pool, self.addToInventory, self.addToErrorLog, event.src_path, self.pdfProcessingData)).start()
    

def processPDF(pool, addToInventory, addToErrorLog, fullFilePath, pdfProcessingData):
    fileName = fullFilePath.split("/")[-1]
    fileLocation = fullFilePath[:-len(fileName)]
    print('File found, processing: '+fileName)
    docs = pool.apply(PDFSplitter, [addToErrorLog, pdfProcessingData, fileLocation, fileName])
    
    if docs == None:
        return

    pool.starmap_async(processDoc, [[addToInventory, addToErrorLog, doc] for doc in docs.values()]).get()
    # for y in docs.values():
        # if "Order Number" in specs:
        #     z = inventoryObject(specs["Order Number"])
        #     z.documents.append(y)
        #     z.specs = specs
        #     self.addToInventory(z, "pdfProcessor")
        # elif y.docType == "Supplement":
            # if "ID" in specs and "Model" in specs:
            #     UID = str(specs["Model"]+specs["ID"])
            #     matchFound = False
            #     for invObj in db.inventory.values():
            #         if "VIN" in invObj.specs and "Model" in invObj.specs:
            #             if str(invObj.specs["Model"]+invObj.specs["VIN"][-6:]) == UID:
            #                 print("UID Matched!")
            #                 invObj.documents.append(y)
            #                 matchFound = True
            #                 break
            #     if matchFound == False:
            #         print("UID Match not found for "+UID)
            #         if UID in db.unknownDocs:
            #             db.unknownDocs[UID].append(y)
            #         else:
            #             db.unknownDocs[UID] = [y]

    # Move original PDF away
    moveToFolder(fileLocation, fileName, OriginalDocsFolder)
    print('Watching for files.', end='\r')


def processDoc(addToInventory, addToErrorLog, doc):
    specs = doc.getSpecs()
    z = inventoryObject(specs["Order Number"] if "Order Number" in specs else "Unknown")
    z.documents.append(doc)
    z.specs = specs
    if "ID" in specs and "Model" in specs:
        z.alternateIDs = {"UID":str(specs["Model"]+specs["ID"])}
    addToInventory(z, "pdfProcessor")


def PDFSplitter(addToErrorLog, pdfProcessingData, pdfLocation, pdfFilename, splitLocation=DocumentsFolder):
    pageGroups = {}  # Pages with no uniqueIdentifier will go to the None entry, where they will be added to an ErroredPages.pdf file and appended to the debug log
    while True:
        try:
            with open(pdfLocation+pdfFilename, 'rb') as do:
                docstream = do.read()
                break
        except:
            print("Attempted to access file too early. Waiting one second.")
            time.sleep(1)
    try:
        doc = fitz.open(stream=docstream, filetype="pdf")
    except Exception as exc:
        addToErrorLog.put(["Could not read file as PDF.", {"File":pdfLocation+pdfFilename, "Error":str(exc)}])
        return

    def getPDFText(filePath, pageToConvert=0):  # pageToConvert set to 0 will convert all pages.
        try:
            fileText = subprocess.run([pdftotextExecutable, '-f', str(pageToConvert), '-l', str(pageToConvert), '-simple', '-raw', filePath,'-'], text=True, stdout=subprocess.PIPE).stdout # convert pdf to text
        except Exception as exc:
            addToErrorLog("getPDFText() failed.", {"Error":str(exc), "File":pdfLocation+pdfFilename})
            return None
        return fileText

    extractedText = getPDFText(pdfLocation+pdfFilename)
    # Stop if no text could be pulled.
    if extractedText == None:
        return
        
    # Create a list of page objects for each page found
    pdfPageList = [page(addToErrorLog, pdfProcessingData, x) for x in extractedText.split('\f')[:-1]]  #last entry will always be empty, as the document will always end with a \f value (formfeed character)
    print("Done making page objects from pdftotext.exe")
    ctime = time.time()

    # Error out if the number of pages found between PyMuPDF and pdftotext.exe do not match.
    if doc.pageCount != len(pdfPageList):
        addToErrorLog("Number of page objects does not equal number of pages found after text conversion", {"Document":pdfLocation+pdfFilename})
        return

    # if self.inDebugFolder == True:
    #     return

    # Create page groups from page invoice numbers
    docs = {}
    for pdfPageNum, pdfPage in enumerate(pdfPageList):
        if pdfPage.invoiceNumber in pageGroups:
            pageGroups[pdfPage.invoiceNumber].addPage(pdfPage)
            docs[pdfPage.invoiceNumber].insertPDF(doc, from_page=pdfPageNum, to_page=pdfPageNum)
        else:
            y = document(addToErrorLog, pdfProcessingData, pdfPage)
            y.invoiceNumber = pdfPage.invoiceNumber
            y.docType = pdfPage.getPageType()
            y.location = str(splitLocation+str(y.docType)+" - "+str(y.invoiceNumber).replace('/','')+".pdf")
            pageGroups[pdfPage.invoiceNumber] = y

            z = fitz.open()
            z.insertPDF(doc, from_page=pdfPageNum, to_page=pdfPageNum)
            docs[pdfPage.invoiceNumber] = z

            
    print("Now writing invoices.")
    # Write problem pages to the Errored Pages pdf.
    if None in pageGroups:
        print("Errored pages!")
        if os.path.exists(DebugFolder+"Errored Pages.pdf"):
            ErroredPagesPDF = fitz.open(DebugFolder+"Errored Pages.pdf")
            ErroredPagesPDF.insertPDF(docs[None])
            ErroredPagesPDF.saveIncr()
        else:
            docs[None].save(DebugFolder+"Errored Pages.pdf")

        # Remove entry for problem pages
        pageGroups.pop(None)
        docs.pop(None)

    # Write PDFs from page groups.
    def writePDFfromSplitter(doc, location):
        attempt = 0
        while True:
            try:
                doc.save(location)
                doc.close()
                break
            except Exception as exc:
                attempt += 1
                if attempt > 10:
                    addToErrorLog("Couldn't save after 10 attempts.", {"Location":location, "Error":exc})
                time.sleep(1)
                print("Error saving: "+location)
    writethreads = [threading.Thread(target=(writePDFfromSplitter), args=([docs[z], pageGroups[z].location])) for z in docs]
    for thread in writethreads:
        thread.start()
    for thread in writethreads:
        thread.join()

    # Send document objects back to main() so inventory objects can be created and sent to the database.
    print("Time taken to split PDF after pdftotext.exe: "+str(time.time()-ctime))
    doc.close()
    return pageGroups






class page(object):
    def __init__(self, errorQueue, pdfProcessingData, text):
        self.errorQueue = errorQueue
        self.pdfProcessingData = pdfProcessingData
        self.text = text
        self.invoiceNumber = None
        try:
            search = reSearchInvoiceNum.search(self.text)
            if search != None:
                self.invoiceNumber = search.group(0)
            elif search == None:
                print(self.text)
            else:
                raise Exception
        except:
            print("Couldn't find invoice num")
            print("First 3 lines:")
            print(self.text.split('\n', 3))
    def getPageType(self):
        lines = self.text.split('\n', self.pdfProcessingData.maxGuideNumber)
        numOfLines = len(lines)
        processingOrder = self.pdfProcessingData.data["ProcessingOrder"]
        fileTypes = self.pdfProcessingData.data["fileTypes"]
        for x in processingOrder:
            if "Guide" in fileTypes[x] and fileTypes[x]["Guide"][0] <= numOfLines:
                lineNumber = fileTypes[x]["Guide"][0]
                for identifier in fileTypes[x]["Guide"][1:]:
                    if identifier in lines[lineNumber-1]:
                        return x


class document(object):
    def __init__(self, errorQueue, pdfProcessingData, pageClass):
        self.errorQueue = errorQueue
        self.pdfProcessingData = pdfProcessingData
        if type(pageClass) == list:
            self.pages = pageClass
        else:
            self.pages = [pageClass]
        ## The following are set by the PDFSplitter function
        self.invoiceNumber = None           # unique document identifier
        self.orderNumber = None             # truck identifier (multiple docs have this)
        # self.VIN = None
        self.docType = None
        self.location = None

    
    def getText(self):
        return "".join(x.text for x in self.pages)

    def addPage(self, pageClass):
        self.pages.append(pageClass)

    def getSpecs(self):
        text = self.getText()

        def findSpecsRecursively(section, txt, parent=0):
            specs = {}
            # Fits my dataset, but likely missing parts that should work for other datasets (ex. using multiline regex with both a Match and a Search)
            # Need to better define process priority.
            if "Defaults" in section:
                specs.update(section["Defaults"])
            if "Search" in section:
                value = section["Search"]
                if type(value) == str:
                    if value not in self.pdfProcessingData.data["SearchLists"]:
                        self.errorQueue("pdfProcessingSettings missing entry in SearchLists.", {"List name":value})
                    else:
                        for x in self.pdfProcessingData.data[value]:
                            specs.update(findSpecsRecursively(x, txt))
                elif type(value) == list:
                    for x in value:
                        specs.update(findSpecsRecursively(x, txt))
            if "Regex" in section:
                if "Multiline" in section and section["Multiline"] == 1:
                    result = section["Regex"].findall(txt)
                    if "Match" in section:
                        if type(section["Match"]) == str and section["Match"] in self.pdfProcessingData.data["MatchLists"]:
                            for x in result:
                                if x[0] in self.pdfProcessingData.data["MatchLists"][section["Match"]]:
                                    for y in self.pdfProcessingData.data["MatchLists"][section["Match"]][x[0]]:
                                        specs.update(findSpecsRecursively(y, x[1]))
                    #elif 
                if "Category" in section:
                    if section["Regex"] == 1:
                        result = txt
                    elif type(section["Regex"]) == re.Pattern:
                        result = section["Regex"].search(txt)
                        if result != None and len(result.groups()) > 0:
                            result = result.group(1)
                        else:
                            return specs
                    if "Replace" in section:
                        if type(section["Replace"]) == str and section["Replace"] in self.pdfProcessingData.data["ReplaceLists"]:
                            if result in self.pdfProcessingData.data["ReplaceLists"][section["Replace"]]:
                                result = self.pdfProcessingData.data["ReplaceLists"][section["Replace"]][result]
                        elif type(section["Replace"]) == dict:
                            if result in section["Replace"]:
                                result = section["Replace"][result]
                    specs[section["Category"]] = result
            return specs

        if self.docType in self.pdfProcessingData.data["fileTypes"]:
            procSet = self.pdfProcessingData.data["fileTypes"][self.docType]
            try:
                return findSpecsRecursively(procSet, text)
            except Exception as exc:
                self.errorQueue("Could not find specs, something went wrong.", {"Error":exc})


class PDFProcessingSettingsObj(object):
    def __init__(self, addToErrorLog):
        self.addToErrorLog = addToErrorLog
        self.fileData = {}          # Unprocessed settings
        self.data = {}              # Settings with RegEx strings converted from a string to re.compile()
        self.maxGuideNumber = 0     # For limiting text splitting when determining file type.
        self.airtableURLFields = ""
        self.loadFromFile()
        self.update()

    def loadFromFile(self):
        try:
            time.sleep(.1)
            with open(SettingsFolder+"pdfProcessingSettings.json", 'r') as clist:
                self.fileData = json.load(clist)
        except Exception as exc:        
            self.addToErrorLog("Could not update from pdfProcessingSettings.json", {"Error":exc})

    def update(self):
        self.data = dict(self.fileData)
        fields = set()
        def recursiveUpdate(part):
            if type(part) == list:
                for x in part:
                    recursiveUpdate(x)  
            elif type(part) == dict:
                for name, value in part.items():
                    if name == "Defaults":
                        for x in value:
                            fields.add(x)
                    elif name == "Category":
                        fields.add(value)
                    elif name == "Regex" and type(value) == str:
                        if "Multiline" in part.keys() and part["Multiline"] == 1:
                            part[name] = re.compile(value, re.M)
                        else:
                            part[name] = re.compile(value, re.S)
                    elif name == "Search" and type(value) == list:
                        recursiveUpdate(value)
                    elif name == "Match" and type(value) == dict:
                        for x in value:
                            recursiveUpdate(value[x])
                    elif name == "Guide" and value[0] > self.maxGuideNumber:
                        self.maxGuideNumber = value[0]

        for x in self.data["fileTypes"].values():
            recursiveUpdate(x)
        for x in self.data["MatchLists"].values():
            for y in x.values():
                recursiveUpdate(y)
        
        # Set the fields used for pulling data from Airtable to the ones we have defined in the processing settings,
        # This is to ensure only editable fields get placed in the specs of an Inventory object
        # otherwise we will encounter errors when outputting to Airtable.
        self.airtableURLFields = "?"+"&".join("fields%5B%5D={}".format(urllib.parse.quote(x)) for x in fields)




    
def getPDFsInFolder(folderLocation):
    filesInFolder = []
    for filename in os.listdir(folderLocation):
        if str(filename)[-3:] == 'pdf':
            filesInFolder.append([folderLocation, filename])
    return filesInFolder



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



# for testing
# if __name__ == "__main__":
#     pool = multiprocessing.Pool()
#     q1 = Queue()
#     q2 = Queue()
#     dog = PDFProcessor(pool,q1,q2)
#     while True:
#         print(q1.get())