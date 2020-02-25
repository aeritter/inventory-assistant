# Airtable Import
## airtable-import.py
This is the main script. Every x seconds, it checks a specific folder for .pdf files. If it finds any, it runs its processes on them to pull out the relevant information for creating a record in Airtable or updating one. It then moves those .pdf files to either the Done folder or the Errored folder, depending on whether the upload to Airtable was successful.

## conversionlists.py
This gets pulled into the main script. It was separated out here to make it easier to read and edit. It contains two Python dictionaries, *headerConversionList* and *dealerCodes*.

### headerConversionList
The Header conversion list has two parts. The first half is the line that would be seen in the .pdf file. The second half is a list containing the header that it would be matched to in Airtable. That list can have either just the one header entry, or it can have sets of two -- the first of which is the header and the second is the RegEx string needed to pull out specific information from the matching line in the .pdf.

#### Example:
Given this line in a .pdf:

`   ENGINE PACKAGE, COMBUSTION       MP7-425M MACK 425HP @ 1500-180`

The script pulls it out into two parts, the first half and the second.
A valid entry in the headerConversionList would look like this:

`'ENGINE PACKAGE, COMBUSTION':['Engine Make',r'^.*? (\w+)','Engine Model',r'^(\S*)'],`

This is interpreted by the script as the following:
If the first half of the line in the .pdf (ENGINE PACKAGE, COMBUSTION) matches the first half of an entry in headerConversionList, it will begin processing using the second half of the matched entry in headerConversionList.

In the above example, this would be the output, with the first entry in every pair being the Airtable header and the second entry being the cell contents:
`{'Engine Make': 'MACK', 'Engine Model': 'MP7-425M'}`

Taking the same line in the .pdf, if you were to use this headerConversionList entry:

`ENGINE PACKAGE, COMBUSTION':['Engine'],`

You would end up with this:

`{'Engine':'MP7-425M MACK 425HP @ 1500-180'}`


To figure out how to match the line using RegEx, go to regex101.com and enter the line you want matched. In this case, you would put `MP7-425M MACK 425HP @ 1500-180` in the bottom half (along with many other entries of the same line if you can) and you would try to match it as best you can using the line above. Use groups. Group 0 is never used in the script, so it begins pulling with group 1.


### dealerCodes
This section contains the dealer codes and their matching location. The location must be an exact match to a location already available as an option in Airtable's Location column.
If the .pdf is an invoice, airtable-import.py will recognize it as such and attempt to match the dealer code found in the document with a location in the dealerCodes dictionary, then make the relevant additions to Airtable.



# Folder Structure

# Settings

# Debugging
