import os.path, csv, wget
from multiprocessing.pool import ThreadPool

imageURLfile = "C:\\imageURLs.csv"
currentinventoryfile = "C:\\currentinventory.csv" # REMOVE ALL BUT THE INVENTORY NUMBERS

with open(imageURLfile, 'r') as f:
    reader = csv.reader(f)
    imageURLs = list(reader)

with open(currentinventoryfile, 'r') as f:
    reader = csv.reader(f)
    currentinventory = set(reader)

listofimages = []
def writeimages(url):
    wget.download(url, "C:\\images\\")

for x in imageURLs:                 # currently set to download to local PC, will eventually change to airtable upload
    if x[0] in currentinventory:
        print("Downloading "+x[0])
        listofimages += x[1]
        

ThreadPool(8).imap_unordered(writeimages, listofimages)

