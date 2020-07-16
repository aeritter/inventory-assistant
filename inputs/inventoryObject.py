class inventoryObject(object): 
    def __init__(self, uniqueIdentifier):
        self.uniqueIdentifier = uniqueIdentifier
        self.documents = []             # refers to document class
        self.specs = None               # dictionary of specs eg. {"Engine Model":"D13"}
        self.alternateIDs = {}          # alternative unique identifiers
        self.airtableRefID = None
    def formatForAirtableUpdate(self):
        return {"id":self.airtableRefID, "fields":self.specs}
    def formatForAirtableCreate(self):
        return {"fields":self.specs}
    def getSpecsFromDocs(self):
        if len(self.documents) == 0:
            raise Exception("self.documents does not contain any information")
        for x in self.documents:
            self.specs.update(x.getSpecs())