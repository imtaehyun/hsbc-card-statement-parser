# HSBC Credit Card Statement PDF Parser

## Library
* [pdf2image](https://github.com/Belval/pdf2image)
    * PDF to Image converter
    * Need to install poppler (check README of repo above)
* [pytesseract](https://github.com/madmaze/pytesseract)
    * Tesseract Python Wrapper

## Process
1. Convert PDF file to Image using PDF2Image
2. Adjust images for improving OCR result
3. Run Tesseract for OCR images
4. Tokenize OCR result
5. Export csv file

## How to run
```bash
> python main.py [-o output_file_path] pdf_file_path
```