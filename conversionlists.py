import re

mainRegex = {   # regex to pull line items out from the pdftotext output
    "Mack":re.compile(r'^(?:   \S{6} {2,6}| {3,5})(?: |(.{2,32})(?<! ) +(.*)\n)', flags=re.M),
    "Volvo":re.compile(r'^ {3,6}(\S{3})\S{3} +. +. +(.*?)(:?  |\d\.\d\n)', flags=re.M),
    "MackInvoice":re.compile(r'^ (\S{3})\S{4} +(.*?) {4,}', flags=re.M),
    "VolvoInvoice":re.compile(r'^(\S{3})\S{4} +(.*?) {2,}?\S', flags=re.M)
    }
distinctInfoRegex = {   # regex to pull field entries directly from the pdftotext output
    "Mack":re.compile(r'^(\w*?) .*?GSO:(.*?) .*?Model Year:(\w+)', flags=re.S),
    "Volvo":'',
    "MackInvoice":re.compile(r'Order Number.*?(\S{4,5}) +(\d{8}).*?UOM.*?(\S{4,6}).*?(\S{17}) ', flags=re.S), 
    "VolvoInvoice":re.compile(r'DEALER\..*?(\S{5}) +.*?NBR:.*?(\S{17}).*?MODEL: +(\S{4}) +.*? SERIAL NBR: (\S{6})', flags=re.S)
}
distinctInfoList = {    # column/field header to match with the associated entry in distinctInfoRegex, in the order that the regex groups are pulled
    "Mack":['Model','Order Number','Year'],
    "Volvo":[],
    "MackInvoice":['Dealer Code','Order Number', 'Model', 'Full VIN'],
    "VolvoInvoice":['Dealer Code', 'Full VIN', 'Year', 'Order Number']
}
make = {                # match filetype with field entry for the Make column
    "Mack":"Mack",
    "Volvo":"Volvo",
    "MackInvoice":"Mack",
    "VolvoInvoice":"Volvo"
}
status = {              # match filetype with field entry for the Status column
    "Mack":"O",
    "Volvo":"O",
    "MackInvoice":"A",
    "VolvoInvoice":"A"
}

headerConversionList = {       
# Mack 
    'ENGINE PACKAGE':['Engine Make',r'^.*? (\w+)', 'Engine Model',r'^(\S*)', 'HP',r'(\d{3}HP)'],
    'ENGINE PACKAGE, COMBUSTION':['Engine Make',r'^.*? (\w+)', 'Engine Model',r'^(\S*)', 'HP',r'(\d{3}HP)'],
    'TRANSMISSION':['Trans Model', '','Transmission',r'(MACK|ALLISON|EATON-FULLER)'],
    'FRONT AXLE':['Front Axle',r'\.*?(\d{5})#'],
    'REAR AXLES - TANDEM':['Rear Axle',r'\.*?(\d{5})#'],
    'REAR AXLE RATIO':['Ratio',r'\.*?(\d.\d\d)'],
    'REAR SUSPENSION - TANDEM':['Suspension',r''],
    'WHEELBASE':['Wheelbase'],
    'TIRES BRAND/TYPE - REAR':['RR Tire Size',r'^.*?(\d\dR.*?) '],
    'WHEELS - FRONT':['FF Wheels',r'(ALUM)'],
    'TIRES BRAND/TYPE - FRONT':['FF Tire Size',r'^.*?(\d\dR.*?) '],
    'WHEELS - REAR':['RR Wheels',r'(ALUM)'],
    'SLEEPER BOX':['Sleeper'],
    'PAINT COLOR - AREA A':['Color'],
    'PAINT COLOR - FIRST COLOR':['Color'],

# Volvo
    '008':['Model'],
    'A19':['Year', r'(\d*?) '],
    '2CX':['Sleeper',r'(\d.*?(?:-ROOF|ROOF)|DAY CAB)'],
    '101':['Engine Make',r'(\w*?) ', 'Engine Model',r'^.*? (\w*?) ', 'HP',r'(\d{3}HP)'],
    '270':['Trans Model','','Transmission',r'(VOLVO|ALLISON)'],
    '330':['Rear Axle',r'.*? (\d.*?)LB'],
    '350':['Suspension'],
    '370':['Front Axle',r'.*? (\d.*?)LB'],
    'TAX':['Ratio',r'(\d\.\d\d)'],
    '400':['Wheelbase',r'(\d*?")'],
    '093':['FF Tire Size',r'^.*?(\d\dR.*?) '],
    '084':['FF Wheels',r'(ALUM|STEEL|(?:POL AL))'],
    '094':['RR Tire Size',r'^.*?(\d\dR.*?) '],
    '085':['RR Wheels',r'(ALUM|STEEL|(?:POL AL))'],
    '980':['Color'],

# Invoices
    '005':['Body'],
    '100':['Engine Model',r'(\w*?) ', 'Engine Make',r'^.*? (\w*?) ', 'HP',r'(\d{3}HP)'],
    '136':['Transmission', r'(ALLISON|MACK|EATON)', 'Trans Model','', 'Trans Model', r'^\S* (\w+\d+.*?) .*$'], # yes, trans model is in here twice for 136. Trans model will be matched to the entire line, then it will be changed if it matches on the second run.
    '016':['Sleeper',r'(.*?)(?:\(|)'],
    '240':['Front Axle',r'.*?(\S*?)#'],
    '268':['Rear Axle',r'.*?(\S*?)#'],
    '271':['Wheelbase'],
    '186':['Suspension',r'(.*?\(|.*)'],
    'FXX':['Front Axle', r'(\d\S*?) LB'],
    'F1X':['Rear Axle', r'(\d\S*?) LB'],
    '900':['FF Tire Size',r'.*?(\d\dR.*?) \S{2,}'],
    '531':['FF Wheels', r'(ALUM|STEEL|POL AL)'],
    '901':['RR Tire Size',r'.*?(\d\dR.*?) \S{2,}'],
    '346':['RR Wheels',r'(ALUM|STEEL|(?:POL AL))'],
    '944':['Color'],

}

dealerCodes = {
    "F292":"Albuquerque",
    "F243":"Amarillo",
    "F278":"Shreveport",
    "F245":"Colorado Springs",
    "F252":"Dallas I-20",
    "F286":"Dallas Irving",
    "F206":"Enid",
    "F283":"Farmington",
    "F239":"Fort Worth",
    "F201":"Greeley",
    "F203":"Garden City", 
    "F703":"Hays",
    "F271":"Hobbs",
    "F264":"Lubbock",
    "F281":"Monroe",
    "F259":"Odessa",
    "F213":"Oklahoma City",
    "F205":"Tulsa East",
    "F284":"Tulsa West",
    "F280":"Tye",
    "F275":"Wichita Falls",
    "F592":"Pineville",

    "4008D":"FedEx",
    "5068D":"Albuquerque",
    "5728D":"Amarillo",
    "5503D":"Shreveport",
    "5037D":"Dallas Irving",
    "5449D":"Dallas I-20",
    "5666D":"Enid",
    "5438D":"Farmington",
    "5708D":"Fort Worth",
    "5657D":"Garden City",
    "5065D":"Hays",
    "5797D":"Hobbs",
    "5886D":"Lubbock",
    "5502D":"Monroe",
    "5746D":"Odessa",
    "5230D":"Oklahoma City",
    "5064D":"Tulsa East",
    "5898D":"Tulsa West",
    "5178D":"Tye",
    "5774D":"Wichita Falls",
    "5460D":"San Angelo",

}

ignoreList = {'EQUIPMENT','ELECTRONICS'}    # unintended RegEx matches that should be ignored