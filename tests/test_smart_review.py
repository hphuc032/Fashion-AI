import pytest
from sqlalchemy import select
from pydantic import ValidationError

from app.core.config import Settings
from app.database.review_schema import ReviewEvent, ReviewState
from app.services.translation_review_service import evaluate, effective_state, review_batch
from app.services.ocr_repository import list_segments,save_reviews
from tests.test_m1_integration import detect_fixture
from app.utils.validators import UserError


def test_curated_high_confidence():
    assert evaluate('男生穿搭','Phối đồ nam',.99).eligible


@pytest.mark.parametrize('source,target,score',[
    ('这件衬衫很舒服','Áo đẹp đấy.',1),('男生穿搭','Phối đồ nam',.9),('男生穿搭','Phối đồ nam',.7),
    ('男生穿搭','',1),('男生穿搭','男生穿搭',1),('价格99元','Giá 98',1),('尺码XL','Cỡ L',1),
    ('Nike衬衫','Áo sơ mi',1),('男生穿搭','Cam kết chính hãng 100%',1),('男生穿搭','nam nam nam nam',1)])
def test_suspicious_stays_pending(source,target,score):
    assert not evaluate(source,target,score).eligible


def test_provider_error():
    assert not evaluate('男生穿搭','Phối đồ nam',1,'failed').eligible


def test_threshold_validation():
    with pytest.raises(ValidationError):
        Settings(auto_review_ocr_low_threshold=.99,auto_review_ocr_high_threshold=.8)


def prepared(m1):
    settings,sessions,project=m1
    segment=detect_fixture(m1)
    save_reviews(sessions,project.id,[dict(id=segment.id,revision=0,translated_text='Phối đồ nam')])
    return settings,sessions,project,list_segments(sessions,project.id)[0]


def test_smart_approval_audit_idempotency_revert(m1):
    settings,sessions,project,s=prepared(m1)
    result=review_batch(sessions,project.id,[dict(id=s.id,revision=s.revision)],'smart',settings)
    assert result['changed']==1
    s=list_segments(sessions,project.id)[0]
    with sessions() as db:
        state=db.get(ReviewState,s.id)
        assert effective_state(s,state)=='AUTO_APPROVED'
        before=len(list(db.scalars(select(ReviewEvent))))
    result=review_batch(sessions,project.id,[dict(id=s.id,revision=s.revision)],'smart',settings)
    assert result['unchanged']==1
    with sessions() as db:
        assert len(list(db.scalars(select(ReviewEvent))))==before
    review_batch(sessions,project.id,[dict(id=s.id,revision=s.revision)],'revert',settings)
    assert list_segments(sessions,project.id)[0].review_status=='pending'


@pytest.mark.parametrize('action',['approve_all','approve_selected'])
def test_confirmation_and_manual_approval(m1,action):
    settings,sessions,project,s=prepared(m1)
    selection=[dict(id=s.id,revision=s.revision)]
    with pytest.raises(UserError,match='xác nhận'):
        review_batch(sessions,project.id,selection,action,settings)
    review_batch(sessions,project.id,selection,action,settings,confirmed=True)
    s=list_segments(sessions,project.id)[0]
    with sessions() as db:
        assert effective_state(s,db.get(ReviewState,s.id))=='MANUALLY_APPROVED'


def test_edited_approval_invalidated(m1):
    settings,sessions,project,s=prepared(m1)
    review_batch(sessions,project.id,[dict(id=s.id,revision=s.revision)],'smart',settings)
    s=list_segments(sessions,project.id)[0]
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text='Nội dung mới',review_status='approved')])
    assert list_segments(sessions,project.id)[0].review_status=='pending'


def test_rejected_protected_and_stale_isolated(m1):
    settings,sessions,project,s=prepared(m1)
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,review_status='rejected')])
    s=list_segments(sessions,project.id)[0]
    result=review_batch(sessions,project.id,[dict(id=s.id,revision=s.revision)],'approve_all',settings,True)
    assert result['unchanged']==1 and list_segments(sessions,project.id)[0].review_status=='rejected'
    result=review_batch(sessions,project.id,[dict(id=s.id,revision=-1)],'revert',settings)
    assert result['failed']==1


def test_batch_limit_and_noop_editor(m1):
    settings,sessions,project,s=prepared(m1)
    settings.auto_review_max_batch_size=1
    with pytest.raises(UserError):
        review_batch(sessions,project.id,[dict(id=s.id,revision=0)]*2,'smart',settings)
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision)])
    assert list_segments(sessions,project.id)[0].revision==s.revision
