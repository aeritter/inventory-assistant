version = '1.1.1'

import re, os.path, subprocess, time, importlib, sys, urllib.parse
import win32file, win32con, win32event, win32net, pywintypes        # watchdog can probably replace all these (pip install watchdog)
import json, requests, multiprocessing, threading, queue, configparser
import fitz # fitz = PyMuPDF
from pathlib import Path
from inputs.inventoryObject import inventoryObject

lock = threading.Lock()
mainFolder = os.path.dirname(os.path.abspath(__file__))+"/"
config = configparser.ConfigParser()
config.read(mainFolder+'settings.ini')


DebugFolder = config['pdfProcessor']['debug_folder']
airtableURLFields = ""
airtableAPIKey = config['Airtable']['airtable_api_key']
airtableURL = config['Airtable']['airtable_url']
slackURL = config['main']['slack_url']
readDirTimeout = int(config['main']['read_dir_timeout'])*1000     # *1000 to convert milliseconds to seconds
debug = config['main'].getboolean('enable_debug')
enableAirtablePosts = config['main'].getboolean('enable_airtable_posts')
enableSlackPosts = config['main'].getboolean('enable_slack_posts')
enableSlackStatusUpdate = config['main'].getboolean('enable_status_update')
CheckinHour = int(float(config['main']['check-in_hour'])*60*60)
TimeBetweenCheckins = float(config['main']['time_between_check-ins_in_minutes'])*60*10000000 #converted to 100 nanoseconds for the function


AirtableAPIHeaders = {
    "Authorization":str("Bearer "+airtableAPIKey),
    "User-Agent":"Python Script",
    "Content-Type":"application/json"
}

class invQueue(object):
    def __init__(self):
        self.queue = multiprocessing.Manager().Queue()
    def addToQueue(self, invObj, source):
        '''invObj = instance of an inventory object
        source = string containing name of object origin'''
        if isinstance(invObj, inventoryObject) and isinstance(source, str):
            self.queue.put([invObj, source])
        else:
            raise TypeError("Expected an inventory object and a string.")

class errQueue(object):  #method, not object????
    def __init__(self):
        self.queue = multiprocessing.Manager().Queue()
    def addToQueue(self, errormsg, **extramessages):
        if isinstance(errormsg, str):
            self.queue.put([errormsg, extramessages])
        else:
            raise TypeError("Expected a string.")

class inputs(object):
    def __init__(self, pool, datastore):
        self.pool = pool
        self.db = datastore
        self.inventoryQueue = invQueue()         # entries to queue.Queue will yield a reference to what is put in
        self.errorQueue = errQueue()   # entries to multiprocessing.Queue will yield a copy of what is put in

        # initialize input modules by adding them here
        from inputs.pdfProcessor import PDFProcessor
        pdfProcessor = threading.Thread(target=(PDFProcessor), args=(self.pool, self.inventoryQueue.addToQueue, self.errorQueue.addToQueue))

        pdfProcessor.start()

        threading.Thread(target=(self.loop_inventoryQueue), daemon=True).start()
        threading.Thread(target=(self.loop_errorQueue), daemon=True).start()

    def loop_inventoryQueue(self):
        while True:
            x = self.inventoryQueue.queue.get()
            if type(x) == list and len(x) == 2:
                if isinstance(x[0], inventoryObject) and isinstance(x[1], str):
                    self.db.addInvObjToInventory(x[0],x[1])
                else:
                    self.errorQueue.queue.put(["Attempted to add an invalid object to inventory."])

    def loop_errorQueue(self):
        while True:
            x = self.errorQueue.queue.get()
            if type(x) == list and type(x[0]) == str:
                if len(x) == 1:
                    appendToDebugLog(x[0])
                elif len(x) == 2 and isinstance(x[1], dict):
                    appendToDebugLog(x[0], **x[1])


class outputs(object):
    def __init__(self):
        self.out = {"airtable":AirtableUpload()}
    def send(self, invobj, source):
        for x in self.out:
            if x != source:
                self.out[x].send(invobj)


class datastore(object):
    def __init__(self):
        self.inventory = {}             # dictionary of inventory UIDs and the corresponding inventory object eg. {"12345":inventoryObject()}
        self.unknownDocs = {}           # format = {"docInvID":[docObj1, docObj2]}
        self.lastUpdated = time.time()
        self.output = outputs()
        global airtableURLFields
        # for x in retrieveRecordsFromAirtable(airtableURLFields):
        #     if "Order Number" in x['fields']:
        #         stockNo = x['fields']['Order Number']       # NOTE: Change from Order Number to Stock Number once applicable.
        #         t = inventoryObject(stockNo)
        #         t.airtableRefID = x['id']
        #         t.specs = x['fields']
        #         self.inventory[stockNo] = t
        #     else:
        #         appendToDebugLog("No Order Number found for Airtable record.", **{"ID":x['id']})

    def addInvObjToInventory(self, newInvObj, source):
        self.lastUpdated = time.time()
        if newInvObj.uniqueIdentifier in self.inventory:
            print("Inventory object exists: "+str(newInvObj.uniqueIdentifier))
            oldInvObj = self.inventory[newInvObj.uniqueIdentifier]

            # add documents from incoming inventory object to existing inventory object if they do not currently exist there
            if newInvObj.documents != None:
                for x in newInvObj.documents:
                    # Compare between the new documents and the old documents, using a list of the contents of each page object's dictionary.
                    found = False
                    for y in oldInvObj.documents:
                        for c in y.__dict__['pages']:
                            for z in x.__dict__['pages']:
                                if z.__dict__ == c.__dict__:
                                    found = True
                    if found == False:
                        print("New doc added to inventory object: "+oldInvObj.uniqueIdentifier)
                        oldInvObj.documents.append(x)
            
            # add incoming specs to existing inventory object
            if newInvObj.specs != None:
                if oldInvObj.specs == None:
                    oldInvObj.specs = newInvObj.specs
                else:
                    oldInvObj.specs.update(newInvObj.specs)
                self.output.send(oldInvObj, source)

        else:
            self.inventory[newInvObj.uniqueIdentifier] = newInvObj
            self.output.send(self.inventory[newInvObj.uniqueIdentifier], source)
            # print("Created Inventory object: "+str(newInvObj.uniqueIdentifier))


class AirtableUpload(object):
    def __init__(self):
        self.entries = queue.Queue()
        self.trigger = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        self.lastSendTime = time.time()
        self.updateList = []
        self.postList = []

    def send(self, entry):
        self.entries.put(entry)
        self.trigger.set()
        self.trigger.clear()

    def upload(self, sendType, content):
        if sendType == "Patch":
            response = requests.patch(airtableURL, data=None, json={"records":[ent.formatForAirtableUpdate() for ent in content]}, headers=AirtableAPIHeaders)
        elif sendType == "Post":
            response = requests.post(airtableURL, data=None, json={"records":[ent.formatForAirtableCreate() for ent in content]}, headers=AirtableAPIHeaders)

        if response.status_code != 200:
            if len(content) == 1:
                appendToDebugLog("Airtable upload failed.", **{"Error":response.text, "Request Type":sendType, "Order Number":content[0].specs["Order Number"]})
            else:
                for x in content:
                    self.upload(sendType, [x])


    def loop(self):
        while True:
            lprint("Airtable uploading process ready for entries to upload.")
            if self.entries.qsize() == 0:
                self.trigger.wait()
            x = 0
            while x < 10:
                time.sleep(0.22)    # time between uploads to Airtable
                if self.entries.qsize() > 0:
                    x = 0
                    try:
                        update = []
                        create = []
                        while len(update) < 10 and len(create) < 10 and self.entries.qsize() > 0:
                            z = self.entries.get()
                            if z.airtableRefID:
                                update.append(z)
                            else:
                                create.append(z)

                        # Need to consolidate these two into a single function
                        if len(update) > 0:
                            self.upload("Patch", update)
                            lprint("Uploaded to Airtable: "+str([ent.uniqueIdentifier for ent in update]))
                        time.sleep(.2)
                        if len(create) > 0:
                            self.upload("Post", create)
                            lprint("Created in Airtable: "+str([ent.uniqueIdentifier for ent in create]))


                    except Exception as exc:
                        appendToDebugLog("Something happened while retrieving data from the Airtable upload queue.", **{"Error":exc})

                # Increment x if nothing left in the queue so we can eventually exit the loop once it's no longer useful to stay in it.
                else:
                    x += 1


def appendToDebugLog(errormsg,**kwargs):
    errordata = str(str(time.ctime())+' '+errormsg + ''.join('\n        {0}: {1!r}'.format(x, y) for x, y in kwargs.items()))
    print(errordata)
    try:
        a = open(DebugFolder+"Debug log.txt", "a+")
        a.write("\n"+errordata)
        a.close()
    except:
        print("Can't append to debug log file.")
    try:
        if enableSlackPosts == True:
            requests.post(slackURL,json={'text':errordata},headers={'Content-type':'application/json'})
    except:
        print("Could not post to Slack!")


def lprint(st):     # NOTE: Worth it to use for all print statements?
    lock.acquire()
    print(st)
    lock.release()


def retrieveRecordsFromAirtable(airtableURLFields="", offset=None):
    while True:
        try:
            # if enableAirtablePosts != True:
            #     return "Airtable connection disabled."
            if offset == None:
                x = requests.get(airtableURL+airtableURLFields, data=None, headers=AirtableAPIHeaders)
            else:
                x = requests.get(airtableURL+airtableURLFields+"{}offset={}".format("?" if airtableURLFields == "" else "&", offset), data=None, headers=AirtableAPIHeaders)

            records = x.json()['records']
            if 'offset' in json.loads(x.text):
                records.extend(retrieveRecordsFromAirtable(offset=json.loads(x.text)['offset']))
            return records
                
        except ConnectionError:
            print("Could not connect to airtable.com")
            time.sleep(30)


def main(pool):
    try:
        # if initialize.Folder_Check() != True:
        #     print("Folder check failed")
        #     raise Exception("Folder check failed")
        

        # NOTE: need initialization phase to populate internal database and ensure folder structure and all necessary files exist
        # NOTE: need reconciliation phase to ensure all outputs contain the latest data

        db = datastore()
        inputs(pool, db)
        print("Done initializing inputs.")

        while True:
            time.sleep(86400)
            if enableSlackPosts == True:
                print("Checking in!       ")
                requests.post(slackURL,json={'text':"{}: Checking-in.".format(time.strftime("%a, %b %d"))},headers={'Content-type':'application/json'})

    except Exception as exc:
        print("main() failed: ",str(exc.args))


if __name__ == "__main__":
    p = multiprocessing.Pool()
    main(p)
