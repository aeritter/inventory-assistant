import requests, json

class airtable(object):

    def __init__(self, APIkey, URL):
        self.APIkey = APIkey
        self.URL = URL
        self.records = None
        self.AirtableAPIHeaders = {
            "Authorization":str("Bearer "+self.APIkey),
            "User-Agent":"Python Script",
            "Content-Type":"application/json"
        }

    def updateRecords(self, fields, offset=None):
        if offset == None:
            x = requests.get(self.URL+fields, data=None, headers=self.AirtableAPIHeaders)
        else:
            x = requests.get(self.URL+fields+"&offset="+offset, data=None, headers=self.AirtableAPIHeaders)
        records = x.json()['records']
        if 'offset' in json.loads(x.text):
            records.extend(self.updateRecords(fields, json.loads(x.text)['offset']))
        self.records = records
        return records

    def getRecordID(self, fieldToMatch=None, cellContentsToMatch=None):
        if self.records == None or fieldToMatch == None or cellContentsToMatch == None:
            raise Exception("getRecordID missing records, fieldToMatch, or cellContentsToMatch")

        for x in self.records:
            if fieldToMatch in x['fields'] and x['fields'][fieldToMatch] == cellContentsToMatch:
                return x['id']
        
    def upload(self, content):
        if type(content) != dict:
            raise TypeError("Value of the Records key does not contain a list")
        if 'records' in content:
            raise Exception("Dictionary does not contain \'records\' key")
        if type(content['records']) == list:
            raise TypeError("Content is not a dictionary")

        if 'id' in (records for records in content['records']):
            x = requests.patch(self.URL,data=None,json=content,headers=self.AirtableAPIHeaders)
            return x
        else:
            x = requests.post(self.URL, data=None,json=content,headers=self.AirtableAPIHeaders)
            return x

    