import argparse
import datetime
import re

import pytesseract
from loguru import logger
from pdf2image import convert_from_bytes


OUTPUT_FILE_PATH = './output/'
LOG_PATH = './log/'
REGEX_LIST = {
    'item_id': '[\dSUIZABl]{1,2}',
    'date': '[\dSUIZABl]{2}',
    'month': '[Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec]+',
    'amount': '[\dSUIZABl]{1,}\.*[\dSUIZABl]{2}[CR]*'
}
# https://ai-facets.org/tesseract-ocr-best-practices/
CONVERT_RULE = {
    'S': '5',
    'I': '1',
    'O': '0',
    'Z': '2',
    'A': '4',
    'B': '8',
    'l': '1'
}


def clean_image(image):
    datas = image.getdata()
    new_data = []
    for item in datas:
        if item[0] != 0 and item[1] != 0 and item[2] != 0:
            new_data.append((255, 255, 255, 0))
        else:
            new_data[-1] = (0, 0, 0)  # make character more thick
            new_data.append(item)
    image.putdata(new_data)
    return image


def adj_number(text):
    result = ''
    for c in text:
        if c in CONVERT_RULE:
            result = result + CONVERT_RULE[c]
        else:
            result = result + c

    return result


def adj_amount(text) -> str:
    if 'CR' in text:
        text = '-' + text.replace('CR', '')

    if '.' not in text:
        text = text[:1] + '.' + text[-2:]

    return text


def extract_transaction_text_list(text) -> list:
    item_re = r'^({})\s*({}\s*{})\s*({}\s*{})\s*(.*)\s+({})$'.format(
        REGEX_LIST['item_id'], REGEX_LIST['date'], REGEX_LIST['month'], REGEX_LIST['date'], REGEX_LIST['month'],
        REGEX_LIST['amount'])
    logger.debug(item_re)
    result = list()
    for line in text.split('\n'):
        regex_result = re.match(item_re, line)
        if regex_result:
            result.append(regex_result.groups())
            logger.debug('{} {}', regex_result.groups(), regex_result.string)

    return result


def tokenize(item):
    # ItemId, Transaction Date, Posting Date, Description, Amount
    result = dict()
    try:
        # item id
        result['id'] = adj_number(item[0])

        # Transaction Date
        date_str = '{} {} {}'.format(adj_number(item[1][:2]), item[1][-3:], '2019')
        result['date'] = datetime.datetime.strptime(date_str, '%d %b %Y').strftime('%Y/%m/%d')

        # Posting Date
        # result['posting_date'] = '{} {}'.format(adj_number(item[2][:2]), item[2][-3:])

        # Description
        result['payee'] = item[3].replace(')))', '').strip()

        # Amount
        amount_str = adj_number(adj_amount(item[4]))
        result['outflow'] = float(amount_str) if float(amount_str) > 0.00 else 0
        result['inflow'] = float(amount_str) * -1 if float(amount_str) < 0.00 else 0

    except Exception as e:
        logger.exception('tokenize error: {}', e)

    return result


def export_csv(item_list, file_name):
    output_file_path = f'{OUTPUT_FILE_PATH}{file_name}'
    field_name = [key for key in item_list[0].keys()]

    import csv
    with open(output_file_path, 'w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, field_name)
        writer.writeheader()
        writer.writerows(item_list)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=str, help='path to input pdf file')
    parser.add_argument("-o", "--output", type=str, help="path to output file (csv)")
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output

    if not output_file:
        output_file = input_file.split('/')[-1].replace('pdf', 'csv')

    logger.debug(f'input_file: {input_file}, output_file: {output_file}')

    with open(input_file, 'rb') as f:
        logger.info('>> convert pdf to image')
        pages = convert_from_bytes(f.read())
        logger.info('Total pages: {}', len(pages))

    filtered_text = list()
    found = False

    logger.info('>> OCR start')
    for idx, page in enumerate(pages):
        logger.info('Page {}', idx + 1)
        ocr_text = pytesseract.image_to_string(clean_image(page))
        logger.debug(ocr_text)
        text_list = extract_transaction_text_list(ocr_text)
        # logger.debug(text_list)
        if text_list:
            filtered_text.extend(text_list)
            found = True
        else:
            if found:
                break

    logger.info('Total transaction item: {}', len(filtered_text))

    logger.info('>> Tokenizing..')
    results = list()
    for item in filtered_text:
        results.append(tokenize(item))

    for item in results:
        logger.debug(item)

    logger.info('>> Exporting...')
    export_csv(results, output_file)
