import argparse
import datetime
import os
import re
import time

import pytesseract
from loguru import logger
from pdf2image import convert_from_bytes

OUTPUT_FILE_PATH = './output/'
LOG_PATH = './log/'
REGEX_LIST = {
    'item_id': '[\dSUIZABOl]{1,2}',
    'date': '[\dSUIZABOl]{2}',
    'month': '(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)+',
    'amount': '[\dSUIZABOl,]{1,}\.*[\dSUIZABOl]{2}[CR]*'
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


def adj_number(text) -> str:
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

    text = text.replace(',', '')

    return text


def extract_transaction_text_list(tran_item_str):
    item_re = r'^({}).*({}\s*{}).*({}\s*{})\s*(.*)\s+({})$'.format(
        REGEX_LIST['item_id'], REGEX_LIST['date'], REGEX_LIST['month'], REGEX_LIST['date'], REGEX_LIST['month'],
        REGEX_LIST['amount'])
    # logger.debug(item_re)

    regex_result = re.match(item_re, tran_item_str)
    if regex_result:
        logger.info('{} {}', regex_result.groups(), regex_result.string)
        return regex_result.groups()
    else:
        return None


def tokenize(tran_item_regex_grp) -> dict:
    # ItemId, Transaction Date, Posting Date, Description, Amount
    result = dict()
    try:
        # item id
        result['id'] = adj_number(tran_item_regex_grp[0])

        # Transaction Date
        date_str = '{} {} {}'.format(adj_number(tran_item_regex_grp[1][:2]), tran_item_regex_grp[1][-3:], '2019')
        result['date'] = datetime.datetime.strptime(date_str, '%d %b %Y').strftime('%Y/%m/%d')

        # Posting Date
        # result['posting_date'] = '{} {}'.format(adj_number(item[2][:2]), item[2][-3:])

        # Description
        result['payee'] = tran_item_regex_grp[3].replace(')))', '').strip()

        # Amount
        amount_str = adj_number(adj_amount(tran_item_regex_grp[4]))
        result['outflow'] = float(amount_str) if float(amount_str) > 0.00 else 0
        result['inflow'] = float(amount_str) * -1 if float(amount_str) < 0.00 else 0

    except Exception as e:
        logger.exception('tokenize error: {}', e)
    # logger.debug(result)
    return result


def export_csv(item_list, file_name):
    output_file_path = f'{OUTPUT_FILE_PATH}{file_name}'
    logger.debug(f'output_file_path: {output_file_path}')
    # If directory is not exist, create directory
    if not os.path.exists(os.path.dirname(output_file_path)):
        os.makedirs(os.path.dirname(output_file_path))

    field_name = [key for key in item_list[0].keys()]

    import csv
    with open(output_file_path, 'w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, field_name)
        writer.writeheader()
        writer.writerows(item_list)


def put_log_to_file(str_list):
    if type(str_list) != list():
        str_list = list(str_list)
    for txt in str_list:
        logger.info(txt)


def setup_file_logger(input_file):
    if not os.path.exists(os.path.dirname(LOG_PATH)):
        os.makedirs(os.path.dirname(LOG_PATH))
    logfile_path = f"{LOG_PATH}{input_file.split('/')[-1].replace('.pdf', '')}_{int(time.time())}.log"
    logger.add(logfile_path, level='DEBUG')


def remove_noise(tran_item_str):
    new_str = ''
    for c in tran_item_str[:16]:
        if c not in '=~-.«':
            new_str = new_str + c
        else:
            new_str = new_str + ' '
    new_str = new_str + tran_item_str[16:]
    new_str = re.sub(r'0ct|Get|Cet', 'Oct', new_str)

    return new_str


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=str, help='path to input pdf file')
    parser.add_argument("-o", "--output", type=str, help="path to output file (csv)")
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output

    if not output_file:
        output_file = input_file.split('/')[-1].replace('pdf', 'csv')

    setup_file_logger(input_file)
    logger.debug(f'input_file: {input_file}, output_file: {output_file}')

    with open(input_file, 'rb') as f:
        logger.info('>> convert pdf to image')
        pages = convert_from_bytes(f.read())
        logger.info('Total pages: {}', len(pages))

    # OCR each page of pdf and extract transaction item string
    filtered_text = list()
    found = False

    logger.info('>> OCR start')
    for idx, page in enumerate(pages):
        logger.info(f'Page {idx + 1}')
        ocr_text = pytesseract.image_to_string(clean_image(page))
        # logger.debug(ocr_text)

        item_re = r'^({})(.*)({})$'.format(
            REGEX_LIST['item_id'], REGEX_LIST['amount'])
        ocr_text_tmp = list()
        for line in ocr_text.split('\n'):
            if re.match(item_re, line):
                ocr_text_tmp.append(line)

        # text_list = extract_transaction_text_list(ocr_text)
        # # logger.debug(text_list)
        if ocr_text_tmp:
            filtered_text.extend(ocr_text_tmp)
            found = True
        else:
            if found:
                break

    put_log_to_file(filtered_text)

    logger.info('>> Tokenizing..')
    results = list()
    for tran_item_str in filtered_text:
        tran_item_str = remove_noise(tran_item_str)
        regex_grp = extract_transaction_text_list(tran_item_str)
        if regex_grp:
            results.append(tokenize(regex_grp))

    logger.info('>> Exporting...')
    export_csv(results, output_file)
