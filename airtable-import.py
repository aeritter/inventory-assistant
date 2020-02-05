import re, os.path, subprocess, time

filefolder = 'C:\\Users\\andrew.ritter\\Desktop\\python-test\\'

def checkfolder():
#    try:
        for x in os.listdir(filefolder):
            subprocess.run(['C:\\pdftotext', '-nopgbrk', filefolder+str(x)]) #convert pdf to text
            filepath = filefolder+str(x)[:-3]+'txt'  #create string of filepath to .txt file
            print(filepath)
            time.sleep(5)

            n = open(filepath, 'r+')                        #from here
            m = n.read().replace('\n', ' ')
            n.close()

            a = open(filepath[:-4]+' edited.txt', 'w')
            a.write(m)
            a.close()                                       #to here, replacing newlines with

            MackOrVolvo(filepath[:-4]+' edited.txt') #begin processing
            print(x)
 #   except:
 #       print("something went wrong")

def removeNewlinesForRegex(input):
    time.sleep(1)



# def MackOrVolvo(file):
#     file = open(file, 'r')
#     thirdline = file.readlines()[2][:6] #take the first 6 characters of line 3
#     if thirdline == "PAGE 1":           #compare it to what is expected of the first 6 characters of line 3 from a Volvo sheet
#         print("Volvo")
#     else:
#         print("Mack")
#     file.close()

def MackImport(file):
    time.sleep(1)
    working = file.readlines()
    print(result)

def VolvoImport(file):
    time.sleep(1)
    

checkfolder()
