
from jaxtyping import Float, Int
from torch import Tensor
from einops import rearrange
import torch
import torch.nn.functional as F

def select_multi_from_tensor(logits: Float[Tensor, 'b h'], choice_ids: Int[Tensor, 'b ...']) -> Float[Tensor, 'b ...']:
    """select from the 2nd dim of a tensor"""
    inds = torch.arange(logits.shape[0]).to(logits.device)
    for _ in range(choice_ids.ndim - 1):
        inds = inds.unsqueeze(-1)
    r = logits[inds, choice_ids.long()]
    return r
