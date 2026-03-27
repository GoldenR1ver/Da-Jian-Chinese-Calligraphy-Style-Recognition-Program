import argparse
import os

parser = argparse.ArgumentParser(description='Hyper-parameters management')

# Hardware options
# NOTE: argparse 里直接使用 `type=bool` 会导致 "False" 也会被当作 True 的问题，
# 因此这里用 `store_true`：传 `--cuda` 才表示启用 CUDA（若可用）。
parser.add_argument('--cuda', action='store_true', help='use cuda if available')
parser.add_argument('--seed', type=int, default=1, help='random seed')

# dataset
DEFAULT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULT = os.path.join(DEFAULT_ROOT, 'result')
parser.add_argument('--root', type=str, default=DEFAULT_ROOT, help='path to data set')
parser.add_argument('--batch_size', type=int, default=512, help='batch size of dataset')
parser.add_argument('--image_size', type=int, default=64, help='resize image')

# model
parser.add_argument('--model', type=str, default='ResNet', help='choose model')

# train
parser.add_argument('--load_state', type=bool, default=False, help='load state from disk')
parser.add_argument('--epochs', type=int, default=50, metavar='N', help='number of epochs to train')
parser.add_argument('--lr', type=float, default=0.01, metavar='LR', help='learning rate')
parser.add_argument('--result', type=str, default=DEFAULT_RESULT, help='path to result')

# Use parse_known_args so importing this module as a package does not fail
# when outer applications pass unrelated CLI flags.
args, _unknown = parser.parse_known_args()

# Normalize paths:
# - `args.root` is expected to be `src/character_recognizer` by default.
# - For backward compatibility, if user passes `--root .../character_recognizer/data`,
#   we treat that as the data directory directly.
_abs_root = os.path.abspath(args.root)
if os.path.basename(_abs_root).lower() == "data":
    BASE_ROOT = os.path.dirname(_abs_root)
    DATA_DIR = _abs_root
else:
    BASE_ROOT = _abs_root
    DATA_DIR = os.path.join(BASE_ROOT, "data")

CHAR_DICT_PATH = os.path.join(DATA_DIR, "char_dict")
RESULT_DIR = os.path.abspath(args.result)
args.root = BASE_ROOT
args.result = RESULT_DIR
