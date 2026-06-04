#!/usr/bin/env bash

#SPM_DIR=/mnt/hieublob2/hieu/workspace/github/marian-internal/build.release
SPM_DIR=/mnt/westus2/hieu/workspace/github/sentencepiece/build/src

VOCAB_SIZE=$1

mkdir -p identity
$SPM_DIR/spm_train --input <(pigz -cd vocab-train.gz) --unk_id=1 --eos_id=0 --bos_id=-1 --pad_id=-1 --add_dummy_prefix=true --character_coverage=1 --split_digits --train_extremely_large_corpus \
        --byte_fallback --normalization_rule_name identity \
        --model_prefix=identity/$VOCAB_SIZE --vocab_size $VOCAB_SIZE 

