import csv
from collections import Counter
from typing import Mapping, Sequence, List, Dict, Tuple
import os
from .core_nlp import SimpleSentence

term_freq_path = os.path.dirname(os.path.realpath(__file__)) + '/../../resources/google_unigram_counts.tsv'

class TermFrequencies(Mapping[str, int]):
    """
    An object that helps with all things related to the counting  / retrieving frequencies of tokens
    """
    def __init__(self, count_mapping: Mapping[str, int], total_count: int):
        self.total_count = total_count
        self._vocab_counts: Counter = Counter(count_mapping)

    @classmethod
    def from_file(cls, vocab_counts_file: str = None) -> 'TermFrequencies':
        """
        :param vocab_counts_file: Path to the vocab count tsv. Format is {token}\t{count}.
        :return: A TermFrequencies object
        """
        if vocab_counts_file is None:
            return cls.canonical()
        print("Reading unigram counts")
        vocab_counts: Dict[str, int] = Counter()
        idx = 0
        with open(vocab_counts_file, 'r', encoding='utf-8') as f:
            csvreader = csv.reader(f, delimiter='\t')
            total_count = int(next(csvreader)[1])
            for row in csvreader:
                idx += 1
                if idx % 100000 == 0:
                    print("Processed {} tokens.".format(idx))
                word = row[0]
                count = int(row[1])
                vocab_counts[word] = count
        return cls(vocab_counts, total_count)

    @classmethod
    def canonical(cls) -> 'TermFrequencies':
        path = term_freq_path
        return cls.from_file(vocab_counts_file=path)

    @classmethod
    def from_sentences(cls, sentences: Sequence[SimpleSentence]) -> 'TermFrequencies':
        """
        Loads a Term Frequencies object by counting tokens in a list of sentences
        :param sentences: A list of sentences
        """
        count: Dict[str, int] = Counter()
        total = 0
        for sentence in sentences:
            for token in sentence.original_texts():
                count[token] += 1
                total += 1

        return cls(count, total)

    def most_common(self, n: int) -> List[Tuple[str, int]]:
        """
        Same behavior as Counter.most_common()
        :param n:
        :return: List of the n most common elements and their counts from the most common to the least.
        """
        return self._vocab_counts.most_common(n)

    def __getitem__(self, item):
        return self._vocab_counts[item]

    def __iter__(self):
        return self._vocab_counts.__iter__()

    def __len__(self):
        return self._vocab_counts.__len__()

    def __contains__(self, o):
        return self._vocab_counts.__contains__(o)

    def keys(self):
        return self._vocab_counts.keys()

    def values(self):
        return self._vocab_counts.values()

    def __eq__(self, other):
        if not isinstance(other, TermFrequencies):
            return NotImplemented
        return self._vocab_counts == other._vocab_counts

    def __ne__(self, other):
        if not isinstance(other, TermFrequencies):
            return NotImplemented
        return self._vocab_counts != other._vocab_counts

    def __add__(self, other: 'TermFrequencies'):
        return self._vocab_counts.__add__(other._vocab_counts)

    @classmethod
    def mock(cls):
        return cls(Counter(["the", "a", "an"]), 3)
