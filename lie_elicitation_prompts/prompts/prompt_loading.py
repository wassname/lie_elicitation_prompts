"""
Modified from https://github.com/EleutherAI/elk/blob/3bbe26c3858aac1b03e6f80628a5056fae44db9c/elk/extraction/prompt_loading.py#L129

Changed to record choices
"""
import multiprocessing
from collections import Counter
from random import Random
from typing import Any, Iterator, Literal, List, Dict
from pathlib import Path

# import datasets
from datasets import ClassLabel, Dataset, Value, load_dataset
import yaml
import numpy as np

# from elk.promptsource.templates import env
from elk.promptsource import DatasetTemplates
from lie_elicitation_prompts.prompts.templates import LocalDatasetTemplates
from elk.utils import (
    assert_type,
    infer_label_column,
    select_split,
)
import datasets
from tqdm.auto import tqdm

from elk.extraction.balanced_sampler import BalancedSampler, FewShotSampler
import pandas as pd
from loguru import logger

from lie_elicitation_prompts.helpers.ds import shuffle_dataset_by
from elk.utils.math_util import stochastic_round_constrained

# Local path to the folder containing the templates
TEMPLATES_FOLDER_PATH = Path(__file__).parent / "templates"


def load_default_sys_instructions(path="system.yaml"):
    f = TEMPLATES_FOLDER_PATH / path
    yaml_dict = yaml.load(f.open("r"), Loader=yaml.FullLoader)
    templates = yaml_dict["templates"]["instructed_to_lie"]
    return templates


default_sys_instructions = load_default_sys_instructions()


def sample_n_true_y_false_prompts(prompts, num_truth=3, num_lie=3, seed=42):
    """sample some truth and some false"""
    df = pd.DataFrame(prompts)

    # restrict to template where the choices are a single token
    # m = df.answer_choices.map(answer_len)<=2
    # df = df[m]
    df = pd.concat(
        [
            df.query("instructed_to_lie==True").sample(
                int(num_truth), random_state=seed
            ),
            df.query("instructed_to_lie==False").sample(
                int(num_lie), random_state=seed
            ),
        ]
    )
    return df.to_dict(orient="records")


def prompt_ok(prompt):
    """we want answers where we can distinguish them from the first token
    we don't have access to the tokenizer here, so we just make sure the first 3 letters are differen't and there are not spaces
    """
    answer_choices = prompt["answer_choices"]
    a = answer_choices[0][:3]
    b = answer_choices[1][:3]
    keep = (a != b) and (" " not in a) and (" " not in b)
    if not keep:
        logger.warning(
            f"removing prompt because it's answers are not unique in first 3 chars or contain space: {prompt['ds_string']} {prompt['template_name']} {prompt['answer_choices']}"
        )
    return keep


import itertools

from itertools import cycle
from typing import Iterable, Optional, Iterator, List, Dict, Any
from random import Random


class FewShotDataset2:
    """A dataset that pre-computes few-shot examples that are as balanced as possible."""

    def __init__(
        self,
        dataset: Iterable,
        num_shots: int,
        rng: Random,
        label_col: Optional[str] = None,
    ):
        self.batches = []  # Store pre-computed batches
        self.num_shots = num_shots
        self.rng = rng
        self.label_col = label_col
        self._prepare_batches(dataset)

    def _prepare_batches(self, dataset):
        neg_buf, pos_buf = [], []
        for sample in cycle(dataset):
            if len(neg_buf) + len(pos_buf) >= len(dataset):
                break  # Prevent infinite loop if dataset is exhausted
            label = sample[self.label_col]
            if label == 0:
                neg_buf.append(sample)
            elif label == 1:
                pos_buf.append(sample)
            else:
                raise ValueError(f"Expected label to be 0 or 1, got {label}")

            neg_count, pos_count = stochastic_round_constrained(
                [self.num_shots / 2, self.num_shots / 2], self.rng
            )
            while len(neg_buf) >= neg_count and len(pos_buf) >= pos_count:
                batch = []
                for _ in range(neg_count):
                    batch.append(neg_buf.pop())
                for _ in range(pos_count):
                    batch.append(pos_buf.pop())

                self.rng.shuffle(batch)
                self.batches.append(batch)

    def __getitem__(self, idx) -> List[Dict[str, Any]]:
        if idx >= len(self.batches):
            idx = idx % len(self.batches)
        return self.batches[idx]

    def __len__(self) -> int:
        return len(self.batches)


def _to_prompts(
    example,
    i,
    binarize,
    label_column,
    prompter,
    rng,
    sys_instructions,
    fewshot_ds,
    ds_string,
    prompt_sampler,
    M,
):
    prompts = _convert_to_prompts(
        example,
        binarize=binarize,
        label_column=label_column,
        prompter=prompter,
        rng=rng,
        sys_instructions=sys_instructions,
        fewshot_ds=fewshot_ds,
        i=i,
    )
    prompts = [{"ds_string": ds_string, "example_i": i, **p} for p in prompts]

    prompts1 = list(filter(prompt_ok, prompts))
    prompts2 = prompt_sampler(prompts1, seed=42 + i, num_truth=M, num_lie=M)
    return {"prompts": prompts2}


def load_prompts(
    ds_string: str,
    *,
    sys_instructions: Dict[bool, Dict[str, str]] = default_sys_instructions,
    binarize: bool = True,
    num_shots: int = 0,
    seed: int = 42,
    split_type: Literal["train", "val"] = "train",
    template_path: str | None = None,
    rank: int = 0,
    world_size: int = 1,
    prompt_sampler=sample_n_true_y_false_prompts,
    N=np.inf,
    M: int = 3,
) -> Iterator[dict]:
    """Load a dataset full of prompts generated from the specified dataset.

    Args:
        ds_string: Name of HF dataset to use, e.g. `"super_glue:boolq"` or `"imdb"`.
        binarize: Whether to binarize the dataset labels for multi-class datasets.
        num_shots: The number of examples to use in few-shot prompts. If zero, prompts
            are zero-shot.
        seed: The seed to use for prompt randomization.
        split_type: Whether to use the train or val split of the dataset.
        template_path: Path to feed into `DatasetTemplates` for loading templates.
        rank: The rank of the current process. Defaults to 0.
        world_size: The number of processes. Defaults to 1.
        prompt_sampler: when given an unbalanced set of true and false prompts this might take one of each randomly
        M: how many true and false forms of each example to keep

    Returns:
        An iterable of prompt dictionaries.
    """
    if Path(ds_string).exists():
        template_path = ds_string
        ds_string = Path(template_path).stem.replace("-", "/")
    ds_name, _, config_name = ds_string.partition(":")

    # load dataset
    ds_dict = assert_type(
        dict, load_dataset(ds_name, config_name or None, trust_remote_code=True)
    )

    # take split
    split_name = select_split(ds_dict, split_type)
    ds = assert_type(Dataset, ds_dict[split_name])
    if world_size > 1:
        ds = ds.shard(world_size, rank)
    N = min(N, len(ds))

    # load dataset templates
    if template_path is None:
        prompter = DatasetTemplates(ds_name, config_name)
    else:
        prompter = LocalDatasetTemplates(template_path)

    # If the prompt template says to binarize, we should
    binarize = binarize or prompter.binarize
    if binarize:
        n = prompter.drop_non_mc_templates()
        if n > 0:
            logger.debug(
                f"dropped {n} templates from {ds_string} because they are not multiple choice"
            )

    num_templates = len(prompter.templates)
    assert num_templates > 0
    if rank == 0:
        logger.info(f"Extracting {num_templates} variants of each prompt")

    # load labels
    label_column = prompter.label_column or infer_label_column(ds.features)

    # if we providing examples, we need to sample them randomly
    rng = Random(seed)
    if num_shots > 0:
        train_name = select_split(ds_dict, "train")

        fewshot_ds = FewShotDataset2(
            ds_dict[train_name]
            .shuffle(seed=seed)
            .select(range(1000)),  # just use a random 1000 repeatedly
            num_shots=num_shots,
            rng=rng,
            label_col=label_column,
        )
    else:
        fewshot_ds = None

    ds1 = ds.select(range(N)).map(
        _to_prompts,
        with_indices=True,
        desc="convert_to_prompts",
        fn_kwargs=dict(
            binarize=binarize,
            label_column=label_column,
            prompter=prompter,
            rng=rng,
            sys_instructions=sys_instructions,
            fewshot_ds=fewshot_ds,
            ds_string=ds_string,
            prompt_sampler=prompt_sampler,
            M=M,
        ),
        #   num_proc=1,#
        num_proc=multiprocessing.cpu_count() // 2,
    )
    return list(itertools.chain(*ds1["prompts"]))



def cast_example_label_to_bool(e, label_column="label"):
    assert e[label_column] >= 0
    assert e[label_column] <= 1
    e[label_column] = bool(e[label_column])
    return e


def _convert_to_prompts(
    example: dict[str, Any],
    prompter: DatasetTemplates,
    binarize: bool,
    label_column: str,
    # label_choices: list[bool | int | str],
    rng: Random,
    sys_instructions: Dict[bool, Dict[str, str]] = default_sys_instructions,
    fewshot_ds: FewShotDataset2 | None = None,
    i: int = 0,
) -> list:
    """Prompt-generating function to pass to `IterableDataset.map`."""

    # FIXME: make mc compat
    example = cast_example_label_to_bool(example, label_column)
    prompts = []
    templates = list(prompter.templates.values())

    # For sanity checking that prompts are unique
    prompt_counter = Counter()
    # label = example[label_column]

    ds_name = prompter.dataset_name
    if prompter.subset_name is not None:
        ds_name += ":" + prompter.subset_name

    # FIXME: not used?
    # if binarize:
    #     # Replace the full list of possibilities with a randomly sampled false label
    #     # and the correct label, as done in the DLK paper. Note that this does add some
    #     # "supervision" by stacking the deck in favor of the correct answer.
    #     logger.info(f"Binarising {label_choices} in {ds_name}")
    #     label_choices = [
    #         rng.choice([c for c in label_choices if c != label]),
    #         label,
    #     ]
    # rng.shuffle(label_choices)

    # FIXME: the original elk is a bit confused between label_choices, and prompt_answer choices. It

    for j, template in enumerate(templates):
        answer_choices = template.get_fixed_answer_choices_list()
        assert len(answer_choices) <= 2, "should be binary"
        if answer_choices is None:
            logger.info(
                f"skipping ds_name={ds_name} template={template.name} because it has no fixed answer choices"
            )
            continue

        # skip prompts where the responses are similar in the first token
        if answer_choices[0][:3] == answer_choices[1][:3]:
            logger.info(
                f"skipping prompt because it's answers are not unique (for the first token): {template.name} {answer_choices}"
            )
            continue
        answer_choices = [[c] for c in answer_choices]
        for instructed_to_lie in [False, True]:
            for sys_instr_name, sys_instr in sys_instructions[
                instructed_to_lie
            ].items():
                instructed_example = example.copy()
                if instructed_to_lie:
                    # FIXME: make multichoice compat
                    instructed_example[label_column] = not bool(
                        instructed_example[label_column]
                    )

                q, a = template.apply(instructed_example)
                messages = [dict(role="user", content=q.strip())]
                prompt_counter[(sys_instr + q, a)] += 1

                if fewshot_ds is not None:
                    # same example for true and false
                    fewshot_examples = fewshot_ds[i + j]
                    # FIXME: make mc compat
                    fewshot_examples = [
                        cast_example_label_to_bool(e, label_column).copy()
                        for e in fewshot_examples
                    ]

                    if instructed_to_lie:
                        # FIXME: make multichoice compat
                        fewshot_examples = [
                            {**e, label_column: not bool(e[label_column])}
                            for e in fewshot_examples
                        ]
                        for e in fewshot_examples:
                            # arg, check negation worked
                            assert e[label_column] >= 0
                            assert e[label_column] < 2
                            assert isinstance(
                                e[label_column], bool
                            ), "labels should be bool"

                    fewshot_texts = []
                    for q, a in map(template.apply, fewshot_examples):
                        fewshot_texts.append(dict(role="user", content=q.strip()))
                        fewshot_texts.append(dict(role="assistant", content=a.strip()))
                        # some of the answers have extra trailing text, that's OK. But extra preceeding text is not, let's check for that
                        aa = a.strip()
                        assert any(
                            [
                                any([aa.startswith(a) for a in ac])
                                for ac in answer_choices
                            ]
                        ), f"fewshot response `{aa}` has extra preceeding text compared to allowed choices: {answer_choices}. template is: {template.name}"
                    messages = fewshot_texts + messages
                messages = [dict(role="system", content=sys_instr)] + messages

                prompts.append(
                    dict(
                        # Strip whitespace from the answer to make it easier to
                        # compare with the model's output
                        answer=a.strip(),
                        messages=messages,
                        answer_choices=answer_choices,
                        template_name=template.name,
                        label_true=example[label_column],
                        instructed_to_lie=instructed_to_lie,
                        sys_instr_name=sys_instr_name,
                        # example_idx=example['idx'],
                    )
                )

    # Sanity check: variants should be unique
    ((maybe_dup, dup_count),) = prompt_counter.most_common(1)
    if dup_count > 1:
        raise ValueError(f'Prompt duplicated {dup_count} times! "{maybe_dup}"')

    return prompts


def load_preproc_datasets(
    dataset_names: List[str],
    N: int,
    split_type: str = "train",
    seed=42,
    num_shots=1,
    M=3,
    num_proc=1,
):
    datasets2 = []
    n = N // len(dataset_names) + 1
    for ds_name in tqdm(dataset_names):
        # if it is a path
        ds_tokens1 = load_preproc_dataset(
            ds_name,
            N=n,
            seed=seed,
            num_shots=num_shots,
            M=M,
            num_proc=num_proc,
        ).with_format("torch")
        datasets2.append(ds_tokens1)
    ds_tokens = datasets.concatenate_datasets(datasets2)

    return ds_tokens


def load_preproc_dataset(
    ds_name: str,
    N: int,
    split_type: str = "train",
    seed=42,
    num_shots=1,
    sys_instructions=default_sys_instructions,
    M=3,
    num_proc=1,
) -> Dataset:
    ds_prompts = Dataset.from_generator(
        load_prompts,
        gen_kwargs=dict(
            ds_string=ds_name,
            num_shots=num_shots,
            split_type=split_type,
            sys_instructions=sys_instructions,
            seed=seed,
            N=N,
            M=M,
        ),
        keep_in_memory=False,
        num_proc=num_proc,
    )
    ds_prompts = shuffle_dataset_by(
        ds_prompts, target="label_true", random_state=seed, stratify_columns=[]
    )
    return ds_prompts
