from paper_monitor.models import Paper
from paper_monitor.openalex import work_to_paper, WORK_FIELDS
from paper_monitor.slack import format_message


def test_title_phrases_replace_author_list_and_keep_tracked_reason():
    p=Paper(title='Less Decoder is More Encoder: Geometric Representation Learning from Novel View Synthesis',
        authors=['Author One','Author Two'],tracked_authors=['Animesh Garg'],sources=['openalex'])
    card=format_message(p);text=card['blocks'][0]['text']['text']
    assert '*Keywords:* Geometric Representation Learning · Novel View Synthesis' in text
    assert 'Author One' not in text and 'Author Two' not in text
    assert 'Tracked: Animesh Garg' in card['blocks'][1]['elements'][0]['text']


def test_source_keywords_and_summary_are_bounded_and_escaped():
    p=Paper(title='A study', keywords=['Robotics','Bayesian optimization','Catalysis','Fourth'])
    text=format_message(p)['blocks'][0]['text']['text']
    assert 'Robotics · Bayesian optimization · Catalysis' in text and 'Fourth' not in text
    p.summary='Uses robotics for screening. A long second sentence with <@U123>.'
    text=format_message(p)['blocks'][0]['text']['text']
    assert 'Uses robotics for screening.' in text and 'second sentence' not in text
    p.summary=None;p.keywords=['<!channel> robotics']
    assert '<!channel>' not in format_message(p)['blocks'][0]['text']['text']


def test_old_records_and_new_openalex_keywords_merge_without_losing_authors():
    old=Paper(title='A study',authors=['Person'])
    new=work_to_paper({'title':'A study','keywords':[{'display_name':'Robotics'}]}, {})
    old.merge(new)
    assert old.keywords==['Robotics'] and old.authors==['Person']
    assert 'keywords' in WORK_FIELDS.split(',')


def test_missing_metadata_does_not_repeat_title_or_invent_keywords():
    p=Paper(title='Catalyst discovery')
    text=format_message(p)['blocks'][0]['text']['text']
    assert text.count('Catalyst discovery')==1 and 'Keywords' not in text
    p.abstract='We report a catalyst screening method. More details follow.'
    assert '*Abstract:* We report a catalyst screening method.' in format_message(p)['blocks'][0]['text']['text']
    p.title='<!channel> Catalyst discovery'
    assert '<!channel>' not in format_message(p)['text']
