from pathlib import Path
from simple_parsing import Serializable, field
from dataclasses import InitVar, dataclass, replace

# Project root directory
ROOT_DIR = Path(__file__).parent.parent

@dataclass
class ExtractConfig(Serializable):
    """Config for extracting hidden states from a language model."""

    datasets: tuple[str, ...] = ("amazon_polarity", "glue:sst2", "super_glue:axg")
    """datasets to use, e.g. `"super_glue:boolq"` or `"imdb"` `"glue:qqp` super_glue:rte super_glue:axg sst2 hans
    note make sure it's an easy task (https://openreview.net/pdf?id=rJ4km2R5t7, https://super.gluebenchmark.com/leaderboard/) and in elk https://github.dev/EleutherAI/elk)
    """    

    datasets_ood: tuple[str, ...] = ( 'imdb', "super_glue:boolq")
    """Out Of Distribution datasets to use, """
    
    model: str = "failspy/Llama-3-8B-Instruct-abliterated"
    """You should use a smart and helpfull>harmless model or you will get hardly any lies."""
    
    num_shots: int = 2
    """Number of examples for few-shot prompts. If zero, prompts are zero-shot."""

    max_tokens: int | None = 776
    """Maximum length of the input sequence passed to the tokenize encoder function"""

    max_examples: tuple[int, int] = 20000
    """Maximum number of examples before truncation and filtering"""

    seed: int = 42
    """Random seed."""

    repeats: int = 3
    """each example if repeated `repeats` times in it's lie and true form"""
