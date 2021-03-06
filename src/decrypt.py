import argparse
import binascii
import logging

from io import BufferedReader, BytesIO
from collections import deque

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter
from pymp4.parser import Box
from pymp4.util import BoxUtil

def main():
    parser = argparse.ArgumentParser(
        description='Python MP4 CENC decrypter'
    )

    parser.add_argument(
        '-k',
        '--key',
        required=True,
        help='AES-128 CENC key in hex',
        type=lambda x: binascii.unhexlify(x)
    )

    parser.add_argument(
        '-i',
        '--input',
        required=True,
        help='Encrypted input MP4',
        type=argparse.FileType('rb')
    )

    parser.add_argument(
        '-o',
        '--output',
        required=True,
        help='Name to output decrypted MP4',
        type=argparse.FileType('wb')
    )

    args = parser.parse_args()

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %I:%M:%S %p',
        level=logging.INFO
    )

    decrypt(args.key, args.input, args.output)
    return


def fix_headers(box):
    """
    fix_headers()

    @param box: pymp4 Box object
    """

    for frma_box in BoxUtil.find(box, b'frma'):
        original_format = frma_box.original_format
    for stsd_box in BoxUtil.find(box, b'stsd'):
        for entry in stsd_box.entries:
            if b'enc' in entry.format:
                entry.format = original_format
    return

def decrypt(key, inp, out):
    """
    decrypt()

    @param key: AES-128 CENC key in bytes
    @param inp: Open input file
    @param out: Open output file
    """

    with BufferedReader(inp) as reader:
        senc_boxes = deque()
        trun_boxes = deque()

        while reader.peek(1):
            box = Box.parse_stream(reader)
            fix_headers(box)

            for stsd_box in BoxUtil.find(box, b'stsz'):
                sample_size = stsd_box.sample_size

            if box.type == b'moof':
                senc_boxes.extend(BoxUtil.find(box, b'senc'))
                trun_boxes.extend(BoxUtil.find(box, b'trun'))
            elif box.type == b'mdat':
                senc_box = senc_boxes.popleft()
                trun_box = trun_boxes.popleft()

                clear_box = b''

                with BytesIO(box.data) as box_bytes:
                    for sample, sample_info in zip(
                        senc_box.sample_encryption_info,
                        trun_box.sample_info
                    ):
                        counter = Counter.new(
                            64,
                            prefix=sample.iv,
                            initial_value=0
                        )

                        cipher = AES.new(
                            key,
                            AES.MODE_CTR,
                            counter=counter
                        )

                        if sample_size:
                            cipher_bytes = box_bytes.read(sample_size)
                            clear_box += cipher.decrypt(cipher_bytes)
                        elif not sample.subsample_encryption_info:
                            cipher_bytes = box_bytes.read(sample_info.sample_size)
                            clear_box += cipher.decrypt(cipher_bytes)
                        else:
                            for subsample in sample.subsample_encryption_info:
                                clear_box += box_bytes.read(subsample.clear_bytes)
                                cipher_bytes = box_bytes.read(subsample.cipher_bytes)
                                clear_box += cipher.decrypt(cipher_bytes)
                box.data = clear_box
            out.write(Box.build(box))
    return

if __name__ == '__main__':
    main()
