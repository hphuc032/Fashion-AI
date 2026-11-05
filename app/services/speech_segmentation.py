import math
from difflib import SequenceMatcher
from app.providers.asr.base import SpeechPhrase
from app.utils.validators import UserError


def normalize_phrases(phrases,offset,duration,existing=()):
    result=list(existing)
    for phrase in phrases:
        if not all(math.isfinite(x) for x in [phrase.start,phrase.end]) or phrase.start<0 or phrase.end<=phrase.start:
            raise UserError('ASR trả timestamp không hợp lệ.')
        if phrase.confidence is not None and (not math.isfinite(phrase.confidence) or not 0<=phrase.confidence<=1):
            raise UserError('ASR trả confidence không hợp lệ.')
        start,end=max(0,phrase.start+offset),min(duration,phrase.end+offset)
        text=phrase.text.strip()
        if not text or end<=start:continue
        if len(text)>1000:raise UserError('ASR trả đoạn quá dài; giảm chunk và thử lại.')
        duplicate=None
        for old in result:
            overlap=min(old.end,end)-max(old.start,start)
            if overlap>0 and SequenceMatcher(None,old.text,text).ratio()>.85:
                duplicate=old;break
        if duplicate:
            # Keep full richer phrase at a chunk boundary, never concatenate twice.
            if len(text)>len(duplicate.text):duplicate.text=text
            duplicate.start=min(start,duplicate.start);duplicate.end=max(end,duplicate.end)
        else:result.append(SpeechPhrase(start,end,text,phrase.confidence,phrase.speaker))
    return sorted(result,key=lambda s:(s.start,s.end,s.text))
