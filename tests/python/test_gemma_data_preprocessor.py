import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../python')))
from gemma_data_preprocessor import GemmaDataProcessor

def test_initialization():
    input_dir = "test_data/input"
    output_dir = "test_data/output"
    os.makedirs(input_dir, exist_ok=True)
    processor = GemmaDataProcessor(input_dir, output_dir)
    assert processor.input_dir == input_dir
    assert processor.output_dir == output_dir

def test_process_all_data():
    input_dir = "test_data/input"
    output_dir = "test_data/output"
    os.makedirs(input_dir, exist_ok=True)
    processor = GemmaDataProcessor(input_dir, output_dir)
    result = processor.process_all_data()
    assert result is not None
    assert isinstance(result, pd.DataFrame)