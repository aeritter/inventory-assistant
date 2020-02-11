import os.path, csv, wget, time
from multiprocessing.pool import ThreadPool

imageURLfile = "C:\\imageURLs.csv"
currentinventoryfile = "C:\\currentinventory.csv" # REMOVE ALL BUT THE INVENTORY NUMBERS

with open(imageURLfile, 'r') as f:
    reader = csv.reader(f)
    imageURLs = list(reader)

with open(currentinventoryfile, 'r') as f:
    currentinventory = set(line.strip() for line in f)

listofimages = []
def writeimages(url):
    print("\n"+url)
    time.sleep(.2)
    wget.download(url, "C:\\images\\")

for x in imageURLs:                 # currently set to download to local PC, will eventually change to airtable upload
    if x[0] in currentinventory:
        listofimages.append(x[1])
        

ThreadPool(12).imap_unordered(writeimages, listofimages)

while True:                         # if this isn't here, the threads will be closed immediately after the above line creates them
    time.sleep(30)

