import nltk


import string
from keras.layers import Dense, Embedding, Input, \
    Bidirectional, Dropout, CuDNNGRU, CuDNNLSTM, PReLU, GRU, \
    Input, Activation, LSTM, GlobalMaxPool1D, BatchNormalization, GlobalMaxPooling1D, \
    Convolution1D, Conv1D, InputSpec, Flatten, GlobalAveragePooling1D, Concatenate, TimeDistributed, Lambda, Conv2D, MaxPool2D, MaxPooling2D, AveragePooling2D, GlobalAveragePooling2D,GlobalMaxPool2D, GlobalMaxPooling2D
from sklearn.model_selection import KFold
from keras import initializers, regularizers, constraints, optimizers, layers
from keras.layers.normalization import BatchNormalization

from keras.layers import concatenate, Dropout, GlobalMaxPool1D, SpatialDropout1D, multiply
from keras.layers import Activation, Lambda, Permute, Reshape, RepeatVector, TimeDistributed
from keras.layers import Embedding, Dense, Bidirectional, Dropout, CuDNNGRU, Input
from keras.callbacks import ModelCheckpoint, EarlyStopping

from keras.layers import Dense, Input, Flatten
from keras.layers import Conv1D, MaxPooling1D, Embedding, Merge, Dropout, LSTM, GRU, Bidirectional, TimeDistributed
from keras.models import Model

from tqdm import tqdm

from keras.preprocessing.text import Tokenizer

def substitute_repeats_fixed_len(text, nchars, ntimes=3):
    return re.sub(r"(\S{{{}}})(\1{{{},}})".format(nchars, ntimes-1), r"\1", text)


def substitute_repeats(text, ntimes=3):
    for nchars in range(1, 20):
        text = substitute_repeats_fixed_len(text, nchars, ntimes)
    return text

def split_text_and_digits(text, regexps):
    for regexp in regexps:
        result = regexp.match(text)
        if result is not None:
            return ' '.join(result.groups())
    return text

def clean_text(df, tokinizer, wrong_words_dict, regexps, autocorrect=True):
    df.fillna("__NA__", inplace=True)
    texts = df.tolist()
    result = []
    for text in tqdm(texts):
        tokens = tokinizer.tokenize(text.lower())
        #tokens = [split_text_and_digits(token, regexps) for token in tokens]
        tokens = [substitute_repeats(token, 3) for token in tokens]
        text = ' '.join(tokens)

        result.append((text))
    return result


def uniq_words_in_text(text):
    return ' '.join(list(set(text.split())))


def delete_unknown_words(text, embeds):
    return ' '.join([word for word in text.split() if word in embeds])



import sys

import pandas as pd
import numpy as np
import os
import re
import numpy as np
import pandas as pd
from multiprocessing import Pool
from keras.preprocessing import text, sequence
import os
import numpy as np
import pandas as pd
import re
import random
import pandas as pd

def load_data(fname, **kwargs):
    func = kwargs.get('func', None)
    if func is not None:
        del kwargs['func']
    df = pd.read_csv(fname, **kwargs)
    if func is not None:
        return func(df.values)
    return df

def convert_text2seq(train_texts, test_texts, max_words, max_seq_len, embeds, lower=True, char_level=False, uniq=False, use_only_exists_words=False, position='pre'):
    tokenizer = Tokenizer(num_words=max_words, lower=lower, char_level=char_level)
    texts = train_texts + test_texts
    if uniq:
        texts = [uniq_words_in_text(text) for text in texts]
    if use_only_exists_words:
        texts = [delete_unknown_words(text, embeds) for text in texts]
    tokenizer.fit_on_texts(texts)
    word_seq_train = tokenizer.texts_to_sequences(train_texts)
    word_seq_test = tokenizer.texts_to_sequences(test_texts)
    word_index = tokenizer.word_index
    word_seq_train = list(sequence.pad_sequences(word_seq_train, maxlen=max_seq_len, padding=position, truncating=position))
    word_seq_test = list(sequence.pad_sequences(word_seq_test, maxlen=max_seq_len, padding=position, truncating=position))
    return word_seq_train, word_seq_test, word_index


def get_embedding_matrix(embed_dim, embeds, max_words, word_index):
    words_not_found = []
    nb_words = min(max_words, len(word_index))
    embedding_matrix = np.zeros((nb_words, embed_dim))
    for word, i in word_index.items():
        if i >= nb_words:
            continue
        embedding_vector = embeds[word]
        if embedding_vector is not None and len(embedding_vector) > 0:
            embedding_matrix[i] = embedding_vector
        else:
            words_not_found.append(word)
    return embedding_matrix, words_not_found


def split_data_idx(n, test_size=0.2, shuffle=True, random_state=0):
    train_size = 1 - test_size
    idxs = np.arange(n)
    if shuffle:
        random.seed(random_state)
        random.shuffle(idxs)
    return idxs[:int(train_size*n)], idxs[int(train_size*n):]


def split_data(x, x_aux, y, test_size=0.2, shuffle=True, random_state=0):
    n = len(x)
    train_idxs, test_idxs = split_data_idx(n, test_size, shuffle, random_state)
    return np.array(x[train_idxs]), np.array(x[test_idxs]), x_aux[train_idxs], x_aux[test_idxs],  y[train_idxs], y[test_idxs], train_idxs, test_idxs

class Embeds(object):
    def __init__(self, fname, w2v_type='fasttext', format='file'):
        if format in ('json', 'pickle'):
            self.load(fname, format)
        elif w2v_type == 'fasttext':
            self.model = self._read_fasttext(fname)
        elif w2v_type == 'glove':
            self.model = self._read_glove(fname)
        else:
            self.model = {}

    def __getitem__(self, key):
        try:
            return self.model[key]
        except KeyError:
            return None

    def __contains__(self, key):
        return self[key] is not None

    def _process_line(self, line):
        line = line.rstrip().split(' ')
        word = line[0]
        vec = line[1:]
        return word, [float(val) for val in vec]
    def _read_glove(self, fname):
        def get_coefs(word, *arr): return word, np.asarray(arr, dtype='float32')
        model = dict(get_coefs(*o.split(' ')) for o in open(fname))
        return model

    def _read_fasttext(self, fname):
        with open(fname) as f:
            # uncomment if first line is vocabulary size and embedding size
            tech_line = f.readline()
            dict_size, vec_size = self._process_line(tech_line)
            print('dict_size = {}'.format(dict_size))
            print('vec_size = {}'.format(vec_size))
            model = {}
            for line in tqdm(f, file=sys.stdout):
                word, vec = self._process_line(line)
                model[word] = vec
        return model



BATCH_SIZE = 256
DENSE_SIZE = 32
RECURRENT_SIZE = 64
DROPOUT_RATE = 0.3
MAX_SENTENCE_LENGTH = 500
OUTPUT_CLASSES = 1
MAX_EPOCHS = 18

UNKNOWN_WORD = "_UNK_"
END_WORD = "_END_"
NAN_WORD = "_NAN_"

CLASSES = ["is_multi_author"]

print("Loading data...")

train = pd.read_csv("/pan_data/train.csv")
test = pd.read_csv("/pan_data/test.csv")
test_ids = test[['id']].values

target_labels = ['is_multi_author']
num_classes = len(target_labels)

# Cleaning things :)

tokinizer = nltk.RegexpTokenizer(r'\S+')
regexps = [re.compile("([a-zA-Z]+)([0-9]+)"), re.compile("([0-9]+)([a-zA-Z]+)")]

# ====Load word vectors====
print('Loading embeddings...')
model = '2dcnn'
if model != 'mvcnn':
    embed_dim = 300
    embeds = Embeds("/camera_data2/glove.840B.300d.txt", "glove", format="text")


print('Generating indirect features...')

###

train['count_word'] = train["comment_text"].apply(lambda x: len(str(x).split()))
test['count_word'] = test["comment_text"].apply(lambda x: len(str(x).split()))
# Unique word count
train['count_unique_word'] = train["comment_text"].apply(lambda x: len(set(str(x).split())))
test['count_unique_word'] = test["comment_text"].apply(lambda x: len(set(str(x).split())))
# Letter count
train['count_letters'] = train["comment_text"].apply(lambda x: len(str(x)))
test['count_letters'] = test["comment_text"].apply(lambda x: len(str(x)))
# punctuation count
train["count_punctuations"] = train["comment_text"].apply(
    lambda x: len([c for c in str(x) if c in string.punctuation]))
test["count_punctuations"] = test["comment_text"].apply(
    lambda x: len([c for c in str(x) if c in string.punctuation]))
# upper case words count
train["count_words_upper"] = train["comment_text"].apply(
    lambda x: len([w for w in str(x).split() if w.isupper()]))
test["count_words_upper"] = test["comment_text"].apply(
    lambda x: len([w for w in str(x).split() if w.isupper()]))
# title case words count
train["count_words_title"] = train["comment_text"].apply(
    lambda x: len([w for w in str(x).split() if w.istitle()]))
test["count_words_title"] = test["comment_text"].apply(
    lambda x: len([w for w in str(x).split() if w.istitle()]))
# Word count percent in each comment:
train['word_unique_pct'] = train['count_unique_word'] * 100 / train['count_word']
test['word_unique_pct'] = test['count_unique_word'] * 100 / test['count_word']
# Punct percent in each comment:
train['punct_pct'] = train['count_punctuations'] * 100 / train['count_word']
test['punct_pct'] = test['count_punctuations'] * 100 / test['count_word']
# Average length of the words
train["mean_word_len"] = train["comment_text"].apply(lambda x: np.mean([len(w) for w in str(x).split()]))
test["mean_word_len"] = test["comment_text"].apply(lambda x: np.mean([len(w) for w in str(x).split()]))
# upper case words percentage
train["words_upper_pct"] = train["count_words_upper"] * 100 / train['count_word']
test["words_upper_pct"] = test["count_words_upper"] * 100 / test['count_word']
# title case words count
train["words_title_pct"] = train["count_words_title"] * 100 / train['count_word']
test["words_title_pct"] = test["count_words_title"] * 100 / test['count_word']
# remove columns

train_df = train.drop('count_word', 1)
train_df = train.drop('count_unique_word', 1)
train_df = train.drop('count_punctuations', 1)
train_df = train.drop('count_words_upper', 1)
train_df = train.drop('count_words_title', 1)

test_df = test.drop('count_word', 1)
test_df = test.drop('count_unique_word', 1)
test_df = test.drop('count_punctuations', 1)
test_df = test.drop('count_words_upper', 1)
test_df = test.drop('count_words_title', 1)

print('Cleaning text...')
train_df['comment_text_clear'] = clean_text(train_df['comment_text'], tokinizer, regexps,
                                            autocorrect=False)
test_df['comment_text_clear'] = clean_text(test_df['comment_text'], tokinizer, regexps,
                                           autocorrect=False)
print('Calc text length...')
train_df.fillna('unknown', inplace=True)
test_df.fillna('unknown', inplace=True)
train_df['text_len'] = train_df['comment_text_clear'].apply(lambda words: len(words.split()))
test_df['text_len'] = test_df['comment_text_clear'].apply(lambda words: len(words.split()))
max_seq_len = np.round(train_df['text_len'].mean() + 3 * train_df['text_len'].std()).astype(int)
print('Max seq length = {}'.format(max_seq_len))

import keras.backend as K

print('Converting texts to sequences...')
max_words = 100000
char_level = False
if char_level:
    max_seq_len = 1200

train_df['comment_seq'], test_df['comment_seq'], word_index = convert_text2seq(
    train_df['comment_text_clear'].tolist(), test_df['comment_text_clear'].tolist(), max_words, max_seq_len, embeds,
    lower=True, char_level=char_level, uniq=True, use_only_exists_words=True, position='post')
print('Dictionary size = {}'.format(len(word_index)))

print('Preparing embedding matrix...')
model = '2dcnn'
if model != 'mvcnn':
    embedding_matrix, words_not_found = get_embedding_matrix(embed_dim, embeds, max_words, word_index)


print('Embedding matrix shape = {}'.format(np.shape(embedding_matrix)))
print('Number of null word embeddings = {}'.format(np.sum(np.sum(embedding_matrix, axis=1) == 0)))

x_aux = np.matrix([
    train_df["word_unique_pct"].tolist(),
    train_df["punct_pct"].tolist(),
    train_df["mean_word_len"].tolist(),
    train_df["words_upper_pct"].tolist(),
    train_df["words_title_pct"].tolist()], dtype='float32').transpose((1, 0))
x = np.array(train_df['comment_seq'].tolist())
y = np.array(train_df[target_labels].values)
x_train_nn, x_test_nn, x_aux_train_nn, x_aux_test_nn, y_train_nn, y_test_nn, train_idxs, test_idxs = \
    split_data(x, np.squeeze(np.asarray(x_aux)),y,test_size=0.2,shuffle=True,random_state=2018)
# test set
test_df_seq = np.array(test_df['comment_seq'].tolist())
test_aux = np.matrix([
    train_df["word_unique_pct"].tolist(),
    train_df["punct_pct"].tolist(),
    train_df["mean_word_len"].tolist(),
    train_df["words_upper_pct"].tolist(),
    train_df["words_title_pct"].tolist()], dtype='float32').transpose((1, 0))
test_df_seq_aux = np.squeeze(np.asarray(test_aux))
y_nn = []
print('X shape = {}'.format(np.shape(x_train_nn)))

print('Run k-fold cross validation...')

kf = KFold(n_splits=10, shuffle=True, random_state=2018)

oof_train = np.zeros((x.shape[0], num_classes))
oof_test_skf = []

filter_sizes=[1,2,3,5]

def _attention_3d_block(inputs, size):
    """Return attention vector evaluated over input. If SINGLE_ATTENTION_VECTOR
    argument is given a temporal mean is taken over the time_step dimension.
    Parameters:
    -----------
    inputs : A tensor of shape (batch_size, time_steps, input_dim).
        Time_steps is represented by the input length, i.e. the number of tokens,
        while input_dim is the number of nodes in the previous nn layer.
    Returns:
    --------
    output_attention :  A tensor of shape (batch_size, time_steps, input_dim),
        representing the attention given to each input token.
    """
    input_dim = int(inputs.shape[2])
    a = Permute((2, 1))(inputs)
    a = Reshape((input_dim, size))(a)
    a = Dense(size, activation='softmax')(a)

    #if self.average_attention:
    a = Lambda(lambda x: K.mean(x, axis=1), name='dim_reduction')(a)
    a = RepeatVector(input_dim)(a)

    a_probs = Permute((2, 1), name='attention_vec')(a)
    output_attention = multiply([inputs, a_probs], name='attention_mul')

    return output_attention


for i, (train_index, test_index) in enumerate(kf.split(x, y)):
    print("TRAIN:", train_index, "TEST:", test_index)

    hidden_units_1 = 128
    hidden_units_2 = 128
    dense_units_1 = 256
    dense_units_2 = 128


    x_train, x_aux_train, x_test, x_aux_test = x[train_index], x_aux[train_index], x[test_index], x_aux[test_index]
    y_train, y_test = y[train_index], y[test_index]

    print('Start training {}-th fold'.format(i))

    inputs = [x_train, x_aux_train]
    inputs_val = [x_test, x_aux_test]

    output_pred = [test_df_seq, test_df_seq_aux]


    text_seq_input = Input(shape=(max_seq_len,))

    embeds = Embedding(embedding_matrix.shape[0],
                       embedding_matrix.shape[1],
                       weights=[embedding_matrix],
                       trainable=False)(text_seq_input)

    xx = SpatialDropout1D(0.3)(embeds)

    xx = Bidirectional(CuDNNGRU(units=hidden_units_1,
                               return_sequences=True))(xx)

    xx = SpatialDropout1D(0.3)(xx)
    xx = Bidirectional(CuDNNGRU(units=hidden_units_2,
                               return_sequences=True))(xx)
    xx = TimeDistributed(Activation('tanh'))(xx)

    attention = _attention_3d_block(inputs=xx, size=max_seq_len)
    dense_input = GlobalMaxPool1D()(attention)

    dense = Dropout(0.2)(dense_input)
    dense = Dense(dense_units_1, activation='elu')(dense)
    dense = Dropout(0.2)(dense)
    dense = Dense(dense_units_2, activation='elu')(dense)
    z = Dropout(0.2)(dense)

    auxiliary_input = Input(shape=(5,), name='aux_input')

    z = Concatenate()([z, auxiliary_input])

    output = Dense(num_classes, activation="sigmoid")(z)

    model = Model(inputs=[text_seq_input, auxiliary_input], outputs=output)

    adam = optimizers.Adam(lr=0.001)
    model.compile(loss='binary_crossentropy', optimizer=adam, metrics=['accuracy'])

    checkpointer = ModelCheckpoint(filepath="weights.fold." + str(0) + ".hdf5",
                                   save_best_only=True,
                                   save_weights_only=True,
                                   monitor='val_loss',
                                   verbose=1)
    earlystopper = EarlyStopping(monitor='val_loss', patience=5, verbose=1)

    history = model.fit(inputs,
                        y_train,
                        epochs=3000,
                        batch_size=128,
                        validation_data=(inputs_val, y_test),
                        callbacks=[earlystopper, checkpointer],
                        shuffle=True)
    model.load_weights(filepath="weights.fold." + str(0) + ".hdf5", by_name=False)
    proba = model.predict(output_pred, batch_size=128)
    oof_train[test_index, :] = model.predict(inputs_val)
    oof_test_skf.append(proba)

np.savetxt("/output/oof_train_glove.csv", oof_train, fmt='%.24f', delimiter=',')
oof_test = np.array(oof_test_skf).mean(axis=0)
np.savetxt("/output/oof_test.csv", oof_test, fmt='%.24f', delimiter=' ')

result = pd.read_csv("/pan_data/sample_submission.csv")
result[target_labels] = oof_test
result.to_csv("/output/pan_glove_sub.csv", index=False)