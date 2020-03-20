# Airtable Import
NOTE: A Python dictionary looks like the following:
```
dictionary = {Key:Value, Key2:Value2}
```
  dictionary is a variable that becomes a dictionary when it is assigned a value of two braces `{}`. It can contain multiple Key:Value pairs, separated by commas. In the case of conversionlists.py, the value for each Key:Value pair is a list. In this situation, that list should contain either one string, or one (or more) pairs of strings and RegEx lines. If the dictionary pair contains just one string as an entry, the entire matching line will be returned for that column. If it contains string/regex pairs, the value that is returned for the column is determined by the RegEx in the second half of the pair.
## airtable-import.py
This is the main script. Every x seconds, it checks a specific folder for .pdf files. If it finds any, it runs its processes on them to pull out the relevant information for creating a record in Airtable or updating one. It then moves those .pdf files to either the Done folder or the Errored folder, depending on whether the upload to Airtable was successful.

## conversionlists.py
This gets pulled into the main script. It was separated out to make it easier to read and edit. It contains a few Python dictionaries, with *headerConversionList* and *dealerCodes* being the ones you will make changes to 99% of the time. The others are for determining how to pull identifier/content pairs from the pdf converted to text. Those will not need to be changed or added to unless Volvo or Mack make changes to their PDF format.

### headerConversionList
The Header conversion list has two parts. The first half is the line that would be seen in the .pdf file. The second half is a list containing the header that it would be matched to in Airtable. That list can have either just the one header entry, or it can have sets of two -- the first of which is the header and the second is the RegEx string needed to pull out specific information from the matching line in the .pdf.

#### Airtable
Airtable receives data in this format:
```
{
  "records": [
    {
      "id": "recIDplacedhere",
      "fields": {
        "Stock": "41991",
        "Year": "2020",
        "Make": "Mack",
        "Model": "LR613"
        }
    }]
} 
```

"records" contains a list of records to create/update. A record is an individual row.

"id" refers to the row ID. This is only present when updating and is obtained from Airtable's API when searching for records.

"fields" contains a list of column names and the entry that goes in that column for that record.


#### Example:
Given this line in a .pdf:

```
   ENGINE PACKAGE, COMBUSTION       MP7-425M MACK 425HP @ 1500-180
```

The script pulls it out into two parts, the first half and the second.
A valid entry in the headerConversionList would look like this:
```
'ENGINE PACKAGE, COMBUSTION':['Engine Make',r'^.*? (\w+)','Engine Model',r'^(\S*)'],
```

This is interpreted by the script as the following:
If the first half of the line in the .pdf (ENGINE PACKAGE, COMBUSTION) matches the first half of an entry (key) in headerConversionList, it will begin processing using the second half (value) of the matched entry in headerConversionList.

In the above example, this would be the output, with the first entry in every pair being the Airtable header and the second entry being the cell contents:
```
{'Engine Make': 'MACK', 'Engine Model': 'MP7-425M'}
```

Taking the same line in the .pdf, if you were to use this headerConversionList entry:

```
ENGINE PACKAGE, COMBUSTION':['Engine'],
```

You would end up with this:
```
{'Engine':'MP7-425M MACK 425HP @ 1500-180'}
```

To figure out how to match the line using RegEx, go to regex101.com and enter the line you want matched. In this case, you would put `MP7-425M MACK 425HP @ 1500-180` in the bottom half (along with many other entries of the same line if you can) and you would try to match it as best you can in the RegEx entry box above. As an example, take that MP7-425M line and use the Engine Make RegEx line with it (the stuff after the r and between the '' (r'in here')) and put them both in regex101.com. Use groups. Group 0 is never used in the script, but it does begin pulling with group 1.


### dealerCodes
This section of conversionlists.py contains the dealer codes and their matching location. The location must be an exact match to a location already available as an option in Airtable's Location column.

For example, this would match the dealer code F243 to the Amarillo location.

`"F243":"Amarillo",`

If the .pdf is an invoice, airtable-import.py will recognize it as such and attempt to match the dealer code found in the document with a location in the dealerCodes dictionary, then make the relevant additions to Airtable.



# Folder Structure
```
Main folder    - Contains the following folders, is the place where PDFs will be placed. PDF name does not matter. If a PDF has been sitting here for a while, there may be a problem in conversionlists.py.
├── Debug            - Contains debug files (pdftotext and regexmatches .txt files) and Debug.txt (which tells you information about errors). You can place a PDF in this folder to have it generate debug files for that PDF, in order to see what the program is pulling from that file.
├── Done             - Contains finished Invoice and Order PDFs. The names for these are automatically determined from their contents.
├── Errored          - Contains PDFs that could not be properly processed for some reason. Check Debug.txt.
├── Settings         - Contains adjustable settings.
|   ├── api_key.txt        - The API key for connecting to the Airtable base.
|   ├── conversionlists.py - Dictionaries containing the values needed to properly pull information from the PDFs and parse and prepare it for Airtable
|   ├── pdftotext.exe      - The program from Xpdf command line tools. Open source. Download from their website. Used to convert the PDFs to text.
|   ├── url.txt            - The URL of the Airtable base and table. Must be obtained from airtable.com/api or it will not work.
|   └── url_fields.txt     - The fields appended to the URL when the program pulls data from Airtable to associate an Airtable record ID with a known constant identifier (in this case, Order Number).
├── Suspended        - Contains PDFs that have been set aside for the time being. Will mostly be supplemental PDFs that are waiting for an Invoice to be appended to.
└── Unsplit TRKINV   - Contains PDFs that consist of multiple invoices. These were placed in the main folder, then moved here after the individual orders were split out and processed.
            
```

# Settings

# Debugging
