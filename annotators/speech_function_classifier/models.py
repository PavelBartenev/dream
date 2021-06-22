import json
import pickle
import re
from collections import defaultdict

import numpy as np
import pandas as pd
import spacy
import torch
from nltk import word_tokenize
from sklearn.linear_model import LogisticRegression
from transformers import AutoTokenizer, AutoModel

nlp = spacy.load("en_core_web_sm")

cuda_is_available = torch.cuda.is_available()

with open('common/speech_functions/res_cor.json') as data:
    file = json.load(data)


def load_pickle(filepath):
    documents_f = open(filepath, 'rb')
    file = pickle.load(documents_f)
    documents_f.close()
    return file


dialogues = []
for d in file[:2]:
    samples = defaultdict(dict)
    result = d['completions'][0]['result']
    texts_without_labels = d['data']['text']
    for sample in result:
        speaker = texts_without_labels[int(sample['value']['start'])]['speaker']
        samples[sample['id']]['speaker'] = speaker
        samples[sample['id']]['text'] = sample['value']['text']
        samples[sample['id']]['start'] = int(sample['value']['start'])
        if 'paragraphlabels' in sample['value']:
            samples[sample['id']]['paragraphlabels'] = sample['value']['paragraphlabels'][0]
        if 'choices' in sample['value']:
            samples[sample['id']]['choices'] = sample['value']['choices'][0]

    sorted_samples = sorted([(samples[sample_id]['start'], sample_id) for sample_id in samples])
    texts = []
    labels = []
    speakers = []
    for _, sample_id in sorted_samples:
        if samples[sample_id]['text'] != 'PAUSE':
            texts.append(str(samples[sample_id]['text']).replace('\n', ''))
            speakers.append(samples[sample_id]['speaker'])
            paragraph_labels = samples[sample_id].get('paragraphlabels', '')
            choices = samples[sample_id].get('choices', '')
            labels.append(paragraph_labels + '.' + choices)
    dialogues.append((texts, labels, speakers))

train_data = dialogues[1][0]
test_data = dialogues[0][0]

train_labels = dialogues[1][1]
test_labels = dialogues[0][1]


def delete_odds(list_with_lines):
    for i in range(len(list_with_lines)):
        if 'them' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace('them', ' them ')
        if ' em ' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace(' em ', ' them ')
        if 'laugh' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace('laugh', '')
        if 'uh?' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace('uh?', '')
        if 'ʔuh' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace('ʔuh', '')
        if 'ʔ' in list_with_lines[i]:
            list_with_lines[i] = list_with_lines[i].replace('ʔ', '')
    return list_with_lines


previous_lines_sust = []
sustains = []
sus_tags = []
for i in range(len(train_data)):
    if 'Sustain' in train_labels[i]:
        previous_lines_sust.append(train_data[i - 1])
        sustains.append(train_data[i])
        sus_tags.append(train_labels[i])
for i in range(len(test_data)):
    if 'Sustain' in test_labels[i]:
        previous_lines_sust.append(test_data[i - 1])
        sustains.append(test_data[i])
        sus_tags.append(test_labels[i])

for i in range(len(sus_tags)):
    if 'Append' in sus_tags[i]:
        sus_tags[i] = re.sub('Append', 'Prolong', sus_tags[i])

sustains = delete_odds(sustains)

responds = []
previous_responds = []
respond_tags = []
for i in range(len(train_data)):
    if 'Answer' in train_labels[i]:
        continue
    if 'Disengage' in train_labels[i]:
        continue
    elif 'Respond' in train_labels[i]:
        responds.append(train_data[i])
        previous_responds.append(train_data[i - 1])
        respond_tags.append(train_labels[i])

for i in range(len(test_data)):
    if 'Answer' in test_labels[i]:
        continue
    if 'Disengage' in test_labels[i]:
        continue
    elif 'Respond' in test_labels[i]:
        responds.append(test_data[i])
        previous_responds.append(test_data[i - 1])
        respond_tags.append(test_labels[i])


def clean_responds(respond_tags):
    for i in range(len(respond_tags)):
        if 'Decline' in respond_tags[i]:
            respond_tags[i] = re.sub('Decline', 'Contradict', respond_tags[i])
        if 'Accept' in respond_tags[i]:
            respond_tags[i] = re.sub('Accept', 'Affirm', respond_tags[i])
        tag_list = respond_tags[i].split('.')[-2:]
        respond_tags[i] = '.'.join(tag_list)
    return respond_tags


respond_tags = clean_responds(respond_tags)

previous_lines = []
replies = []
tags = []
for i in range(len(train_data)):
    if 'Reply' in train_labels[i]:
        if '?' not in train_labels[i]:
            previous_lines.append(train_data[i - 1])
            replies.append(train_data[i])
            tags.append(train_labels[i])

for i in range(len(test_data)):
    if 'Reply' in test_labels[i]:
        if '?' not in test_labels[i]:
            previous_lines.append(test_data[i - 1])
            replies.append(test_data[i])
            tags.append(test_labels[i])

for i in range(len(tags)):
    tag_list = tags[i].split('.')[-2:]
    tags[i] = str('.'.join(tag_list))
    if 'Answer' in tags[i]:
        tags[i] = 'Response.Resolve.'

train_speakers = dialogues[1][2]
test_speakers = dialogues[0][2]

train_data = delete_odds(train_data)
test_data = delete_odds(test_data)


def get_cut_labels(labels):
    for i in range(len(labels)):
        if labels[i].startswith('Open'):
            labels[i] = 'Open.'
        if labels[i].startswith('React.Rejoinder.'):
            labels[i] = 'React.Rejoinder.'
        if labels[i].startswith('React.Respond.'):
            labels[i] = 'React.Respond.'
        if labels[i].startswith('Sustain.Continue.'):
            labels[i] = 'Sustain.Continue.'
    return labels


cut_train_labels = get_cut_labels(train_labels)

cut_test_labels = get_cut_labels(test_labels)

tokenizer = AutoTokenizer.from_pretrained("DeepPavlov/bert-base-cased-conversational")
embed_model = AutoModel.from_pretrained("DeepPavlov/bert-base-cased-conversational")

if cuda_is_available:
    embed_model.to('cuda')


def get_embeddings(data):
    outputs = []
    for text in data:
        with torch.no_grad():
            input_ph = tokenizer(text, padding=True, truncation=True, max_length=30, return_tensors="pt")
            if cuda_is_available:
                input_ph.to('cuda')
            output_ph = embed_model(**input_ph)
    #        train_outputs.append(output_ph.pooler_output.cpu().numpy())
            sentence_embedding = output_ph.last_hidden_state.mean(dim=1).cpu().numpy()
        outputs.append(sentence_embedding)
    outputs = np.concatenate(outputs)
    return outputs


all_outputs = []
all_outputs.extend(get_embeddings(train_data))
all_outputs.extend(get_embeddings(test_data))

all_cuts = []
all_cuts.extend(cut_train_labels)
all_cuts.extend(cut_test_labels)

path2 = 'SBC058.json'
with open(path2) as proba:
    proba = json.load(proba)
    dialogue = proba['text']
    dialogue = [i for i in dialogue if not (i['phrase'] == 'PAUSE')]
    phrases = []
    speakers = []
    for i in range(len(dialogue)):
        phrases.append(dialogue[i]['phrase'])
        speakers.append(dialogue[i]['speaker'])

phrases = delete_odds(phrases)

model = LogisticRegression(C=0.01, class_weight='balanced')
model.fit(all_outputs, all_cuts)


def upper_class_predict(phrase_embeddings, model):
    y_pred_sample = model.predict(phrase_embeddings)
    return y_pred_sample


def number_of_specific_entities(sent):
    entity_dict = {
        'PERSON': 0, 'NORP': 0, 'FAC': 0, 'ORG': 0, 'GPE': 0, 'LOC': 0,
        'PRODUCT': 0, 'EVENT': 0, 'WORK_OF_ART': 0, 'LAW': 0, 'LANGUAGE': 0,
        'DATE': 0, 'TIME': 0, 'PERCENT': 0, 'MONEY': 0, 'QUANTITY': 0,
        'ORDINAL': 0, 'CARDINAL': 0}
    entities = [ent.label_ for ent in sent.as_doc().ents]
    for entity in entities:
        entity_dict[entity] += 1
    return entity_dict


def number_of_fine_grained_pos_tags(sent):
    tag_dict = {'-LRB-': 0, '-RRB-': 0, ',': 0, ':': 0, '.': 0, "''": 0, '""': 0, '#': 0,
                '``': 0, '$': 0, 'ADD': 0, 'AFX': 0, 'BES': 0, 'CC': 0, 'CD': 0, 'DT': 0,
                'EX': 0, 'FW': 0, 'GW': 0, 'HVS': 0, 'HYPH': 0, 'IN': 0, 'JJ': 0, 'JJR': 0,
                'JJS': 0, 'LS': 0, 'MD': 0, 'NFP': 0, 'NIL': 0, 'NN': 0, 'NNP': 0, 'NNPS': 0,
                'NNS': 0, 'PDT': 0, 'POS': 0, 'PRP': 0, 'PRP$': 0, 'RB': 0, 'RBR': 0, 'RBS': 0,
                'RP': 0, '_SP': 0, 'SYM': 0, 'TO': 0, 'UH': 0, 'VB': 0, 'VBD': 0, 'VBG': 0,
                'VBN': 0, 'VBP': 0, 'VBZ': 0, 'WDT': 0, 'WP': 0, 'WP$': 0, 'WRB': 0, 'XX': 0,
                'OOV': 0, 'TRAILING_SPACE': 0}
    for token in sent:
        if token.is_oov:
            tag_dict['OOV'] += 1
        elif token.tag_ == '':
            tag_dict['TRAILING_SPACE'] += 1
        else:
            tag_dict[token.tag_] += 1

    return tag_dict


def divide_into_sentences(document):
    return [sent for sent in document.sents]


nn_classifier = load_pickle('nn_classifier.pickle')
scaler = load_pickle('scaler.pickle')


def predict(test_sent):
    parsed_test = divide_into_sentences(nlp(test_sent))
    # Get features
    sentence_with_features = {}
    entities_dict = number_of_specific_entities(parsed_test[0])
    sentence_with_features.update(entities_dict)
    pos_dict = number_of_fine_grained_pos_tags(parsed_test[0])
    sentence_with_features.update(pos_dict)
    # dep_dict = number_of_dependency_tags(parsed_test[0])
    # sentence_with_features.update(dep_dict)
    df = pd.DataFrame(sentence_with_features, index=[0])
    df = scaler.transform(df)

    prediction = nn_classifier.predict(df)
    if prediction == 0:
        open_tag = 'Fact'
    else:
        open_tag = 'Opinion'
    return open_tag


def get_open_labels(phrase, y_pred):
    open_tag = predict(phrase)
    if open_tag == 'Fact':
        if '?' not in phrase:
            open_tag = 'Give.Fact.'
        else:
            open_tag = 'Demand.Fact.'
    else:
        if '?' not in phrase:
            open_tag = 'Give.Opinion.'
        else:
            open_tag = 'Demand.Opinion.'
    y_pred = y_pred + open_tag
    if len(word_tokenize(phrase)) < 4:
        poses = []
        doc = nlp(phrase)
        for token in doc:
            poses.append(token.pos_)
        if 'PROPN' in poses:
            y_pred = 'Open.Attend'
    return y_pred


def check_develop(y_pred, y_pred_previous, current_speaker, previous_speaker):
    if current_speaker != previous_speaker:
        if 'Sustain.Continue.' in y_pred_previous:
            if 'Sustain.Continue.' in y_pred:
                y_pred = 'React.Respond.Develop.'
    return y_pred


train_sustains = get_embeddings(sustains)

lr_sus = LogisticRegression(C=0.01, class_weight='balanced')
lr_sus.fit(train_sustains, sus_tags)


def get_label_for_sustains(phrase, y_pred):
    test_sustains = []
    test_sustains.append(phrase)
    test_sustains_emb = get_embeddings(test_sustains)
    tags_for_sus = lr_sus.predict(test_sustains_emb)
    if y_pred == 'Sustain.Continue.':
        y_pred = ''.join(tags_for_sus)
    if y_pred == 'React.Respond.Develop.':
        cut_tags = ''.join(tags_for_sus).split('.')[-1]
        if cut_tags != 'Monitor':
            y_pred += cut_tags
    return y_pred


def map_tracks(tags_for_track):
    true_tracks = {'1': 'Track.Check', '2': 'Track.Confirm', '3': 'Track.Clarify', '4': 'Track.Probe'}
    for i in range(len(list(tags_for_track))):
        if tags_for_track[i] == '5':
            tag = tags_for_track[i]
        else:
            tag = true_tracks[tags_for_track[i]]
    return tag


lr2 = LogisticRegression(C=0.01, class_weight='balanced')

with open('track_list') as track_list:
    track_list = track_list.readlines()
train_que = []
train_tags = []
for line in track_list:
    line = line.split('/')
    train_que.append(line[0])
    train_tags.append(line[1][:-1])

train_em_que = get_embeddings(train_que)

lr2.fit(train_em_que, train_tags)


def get_label_for_question(phrase, y_pred, current_speaker, previous_speaker):
    interrogative_words = ['whose', 'what', 'which', 'who', 'whom', 'what', 'which', 'why', 'where', 'when', 'how']
    questions = list()
    questions.append(phrase)
    question_embeddings = get_embeddings(questions)
    y_pred_track = lr2.predict(question_embeddings)
    tag_for_track = map_tracks(y_pred_track)
    if current_speaker != previous_speaker:
        if y_pred == 'React.Respond.' and tag_for_track != '5':
            y_pred = 'React.Rejoinder.' + tag_for_track
        if y_pred == 'React.Rejoinder.' and tag_for_track != '5':
            y_pred += tag_for_track
        if y_pred == 'React.Rejoinder.' and tag_for_track == '5':
            for word in interrogative_words:
                if word in phrase:
                    y_pred = 'React.Rejoinder.Rebound'
                else:
                    y_pred = 'React.Rejoinder.Re-challenge'
        if y_pred == 'Sustain.Continue.':
            y_pred = 'React.Rejoinder.' + tag_for_track
        if y_pred == 'Open.':
            pass
    if current_speaker == previous_speaker:
        if y_pred == 'React.Rejoinder.' and tag_for_track != '5':
            y_pred += tag_for_track
        if y_pred == 'React.Rejoinder.' and tag_for_track == '5':
            for word in interrogative_words:
                if word in phrase:
                    y_pred = 'React.Rejoinder.Rebound'
                else:
                    y_pred = 'React.Rejoinder.Re-challenge'
        if y_pred == 'Open.':
            pass
        if y_pred == 'Sustain.Continue.':
            y_pred = 'Sustain.Continue.Monitor'
    return y_pred


train_embed_replies = get_embeddings(replies)
train_prev_lines = get_embeddings(previous_lines)
reply_concatenate = np.concatenate([train_embed_replies, train_prev_lines], axis=1)

lr_reply = LogisticRegression(C=0.01, class_weight='balanced')
lr_reply.fit(reply_concatenate, tags)

train_emb_responds = get_embeddings(responds)
train_prev_responds = get_embeddings(previous_responds)
responds_concatenate = np.concatenate([train_emb_responds, train_prev_responds], axis=1)

lr_responds = LogisticRegression(C=0.5, class_weight='balanced')
lr_responds.fit(responds_concatenate, respond_tags)


def get_label_for_responds(phrase, previous_phrase, y_pred, y_pred_previous, current_speaker, previous_speaker):
    try_replies = []
    test_prev_lines = []
    test_responds = []
    test_responds_prev_lines = []
    if '?' in previous_phrase:
        if current_speaker != previous_speaker:
            test_prev_lines.append(previous_phrase)
            try_replies.append(phrase)
            test_concat = np.concatenate([get_embeddings(try_replies), get_embeddings(test_prev_lines)], axis=1)
            tag_for_reply = lr_reply.predict(test_concat)
            y_pred = y_pred + ''.join(tag_for_reply)
            if 'yes' in str(try_replies).lower():
                if y_pred == 'React.Respond.Reply.Disagree':
                    if 'Confirm' in y_pred_previous:
                        y_pred = 'React.Respond.Reply.Affirm'
        else:
            test_responds_prev_lines.append(previous_phrase)
            test_responds.append(phrase)
            test_responds_concatenate = np.concatenate(
                [get_embeddings(test_responds), get_embeddings(test_responds_prev_lines)], axis=1)
            tags_for_responds = lr_responds.predict(test_responds_concatenate)
            y_pred = y_pred + ''.join(tags_for_responds)
            if ' no ' in str(test_responds).lower():
                y_pred = 'Rejoinder.Counter'

    else:
        test_responds_prev_lines.append(previous_phrase)
        test_responds.append(phrase)
        test_responds_concatenate = np.concatenate(
            [get_embeddings(test_responds), get_embeddings(test_responds_prev_lines)], axis=1)
        tags_for_responds = lr_responds.predict(test_responds_concatenate)
        y_pred = y_pred + ''.join(tags_for_responds)
        if ' no ' in str(test_responds).lower():
            y_pred = 'Rejoinder.Counter'
    return y_pred


def get_labels_for_rejoinder(phrase, previous_phrase, current_speaker, previous_speaker):
    if ' no ' in phrase.lower():
        return 'React.Rejoinder.Counter'
    if '?' in previous_phrase:
        if previous_speaker != current_speaker:
            y_pred = 'React.Rejoinder.Response.Resolve'
        else:
            y_pred = 'React.Rejoinder.Re-challenge'
    else:
        y_pred = 'React.Respond.Develop.Extend'
    return y_pred


# тут вся классификация
y_preds = []


def get_speech_function(phrase, prev_phrase, prev_speech_function, speaker='John', previous_speaker='Doe'):
    # note: default values for current and previous speaker are only to make them different. In out case they are always
    # different (bot and human)
    test_embeddings = get_embeddings([phrase])
    y_pred = ''.join(list(upper_class_predict(test_embeddings, model)))
    if prev_phrase is None:
        y_pred = get_open_labels(phrase, 'Open.')
    else:
        if y_pred == 'Open.':
            y_pred = get_open_labels(phrase, y_pred)
        if y_pred == 'Sustain.Continue.':
            y_pred = check_develop(y_pred, prev_speech_function, speaker, previous_speaker)
            y_pred = get_label_for_sustains(phrase, y_pred)
        if '?' in phrases[i]:
            y_pred = get_label_for_question(phrase, y_pred, speaker, previous_speaker)
        if y_pred == 'React.Respond.':
            y_pred = get_label_for_responds(phrase, prev_phrase, y_pred, prev_speech_function, speaker,
                                            previous_speaker)
        if y_pred == 'React.Rejoinder.':
            y_pred = get_labels_for_rejoinder(phrase, prev_phrase, speaker, previous_speaker)
    return y_pred


if __name__ == '__main__':
    import nltk
    nltk.download('punkt')
