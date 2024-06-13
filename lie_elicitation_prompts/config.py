from pathlib import Path
from simple_parsing import Serializable, field
from dataclasses import InitVar, dataclass, replace

# Project root directory
ROOT_DIR = Path(__file__).parent.parent

@dataclass
class ExtractConfig(Serializable):
    """Config for extracting hidden states from a language model."""

    datasets: tuple[str, ...] = ("amazon_polarity", "glue:qnli")
    """datasets to use, e.g. `"super_glue:boolq"` or `"imdb"` `"glue:qnli` super_glue:rte super_glue:axg sst2 hans"""

    datasets_ood: tuple[str, ...] = ( 'imdb', "super_glue:boolq")
    """Out Of Distribution datasets to use, e.g. `"super_glue:boolq"` or `"imdb"` `"glue:qnli"""
    
    model: str = "failspy/Llama-3-8B-Instruct-abliterated"
    """You should use a smart and helpfull>harmless model or you will get hardly any lies."""
    
    num_shots: int = 2
    """Number of examples for few-shot prompts. If zero, prompts are zero-shot."""

    max_tokens: int | None = 776
    """Maximum length of the input sequence passed to the tokenize encoder function"""

    max_examples: tuple[int, int] = 3000
    """Maximum number of examples"""

    seed: int = 42
    """Random seed."""
