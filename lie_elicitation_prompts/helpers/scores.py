
from typing import Optional, List, Tuple, Dict
import numpy as np
import functools
import itertools
from transformers import (
    PreTrainedTokenizer,
    PreTrainedModel
)
from jaxtyping import Float, Int
from torch import Tensor
from einops import rearrange
import torch

from lie_elicitation_prompts.helpers.select import select_multi_from_tensor


@functools.lru_cache()
def choice2id(tokenizer, c: str, whitespace_first=False) -> List[int]:
    """convert a choice to a single token"""
    # HACK: this whole function is messy, and specific to the llama tokenizer :(. I don't want it to fail silently, so I'm adding a few asserts. It's better to find out before 4 hours of data collection
    
    # Note some tokenizers differentiate between "yes", "\nyes" and " yes", and ideally we want all! 
    ids2 = []
    ids2 += tokenizer(f' {c}', add_special_tokens=False)["input_ids"]
    ids2 += tokenizer(f'\n{c}', add_special_tokens=False)["input_ids"]
    ids2 += tokenizer(f'{c}', add_special_tokens=False)["input_ids"]
    ids = list(set(ids2))
    
    # only include ones that decode to our original
    ids = [i for i in ids if c.strip().startswith(tokenizer.decode(i).strip()) and len(tokenizer.decode(i).strip())]
    assert len(ids)
    
    # QC: they should all decode to the same token
    decoded_ids = tokenizer.batch_decode(ids)
    shortest = sorted(decoded_ids, key=lambda s:len(s))[0]
    assert len(shortest)
    assert all([decoded_ids[i].strip().startswith(shortest) for i in range(len(decoded_ids))]), f"decoded_ids={decoded_ids}"
    
    # check that we can decode it
    c3 = tokenizer.batch_decode(ids)
    for c2 in c3:
        if not c.strip().startswith(c2.strip()) and len(c2):
            print(c, c2, c3)
            ids = tokenizer(c, add_special_tokens=False)["input_ids"]
            decoded_ids = [tokenizer.decode(i).strip() for i in ids]
            print(f"{c}=>{ids}=>{decoded_ids}")
            raise AssertionError(f'We should be able to encode and decode the choices, but it failed: tokenizer.decode(tokenizer(`{c}`))==`{c2}`!=`{c}`')
    return ids

def choice2ids(all_choices: List[List[str]], tokenizer: PreTrainedTokenizer) -> List[List[int]]:
    choices = [list(itertools.chain(*[choice2id(tokenizer, c) for c in choices])) for choices in all_choices]
    assert choices[0]!=choices[1], f"choices should be different but were not {all_choices}"
    assert choices[0][0]!=choices[1][0], "choices should be different"
    return choices


def row_choice_ids(r, tokenizer):
    return choice2ids([c for c in r['answer_choices']], tokenizer)

def select_choice_from_logits(logits, choiceids: List[List[int]]):
    """calculate the probability for each group of choices."""
    assert logits.ndim==1, f"expected logits to be 1d, got {logits.shape}"
    assert logits.sum(0).abs()>2, 'pass in logits, not probs. you may have accidentally passed in a softmaxed values'
    choiceids = [list(set(i)) for i in choiceids] # we don't want to double count
    probs = logits.softmax(0)  # shape [tokens, inferences)
    probs_c = torch.tensor([[probs[cc] for cc in c] for c in choiceids]).sum(1)  # sum over alternate choices e.g. [['decrease', 'dec'],['inc', 'increase']]
    assert probs_c.sum()<=1.01, f"expected probs to be less than 1, as it's a selection from probs that add to 1"
    return probs_c


def sum_select_choices_from_logits(logits_last: Float[Tensor, 'b h'], choice_ids: Int[Tensor, 'b c n']) -> Float[Tensor, 'b c']:
    """sum the logits for each set of choices"""
    bs = logits_last.shape[0]
    device = logits_last.device
    probs = logits_last.softmax(1)

    # flatten
    flat_choice_ids = rearrange(choice_ids, 'b c n -> b (c n)').to(device)

    # select
    flat_choice_probs = select_multi_from_tensor(probs, flat_choice_ids)

    # unflatten
    choice_probs = rearrange(flat_choice_probs, 'b (c n) -> b c n', c=choice_ids.shape[1]).sum(2)
    return choice_probs
