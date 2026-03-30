import chardet

with open("Dump20260131 (6).sql", "rb") as f:
    data = f.read(1000)
    print(chardet.detect(data))
