import json
from datetime import datetime
from jsonschema import Draft202012Validator, FormatChecker

ENTITY = {'type': 'object', 'required': ['id', 'name'], 'properties': {
    'id': {'type': 'string', 'minLength': 1}, 'name': {'type': 'string', 'minLength': 1}}}
SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object', 'required': ['schema_version', 'run_id', 'created_at', 'experiment', 'variant', 'metrics', 'view'],
    'properties': {
        'schema_version': {'const': '2.0'}, 'run_id': {'type': 'string', 'minLength': 1},
        'created_at': {'type': 'string', 'format': 'date-time'}, 'experiment': ENTITY,
        'variant': {**ENTITY, 'required': ['id', 'name', 'kind'], 'properties': {
            **ENTITY['properties'], 'kind': {'enum': ['baseline', 'ablation', 'modification']},
            'description': {'type': 'string'}, 'baseline_id': {'type': 'string'}}},
        'config': {'type': 'object'},
        'metrics': {'type': 'object', 'minProperties': 1, 'additionalProperties': {
            'type': 'object', 'required': ['label', 'unit', 'direction', 'role'], 'properties': {
                'label': {'type': 'string', 'minLength': 1}, 'unit': {'type': 'string'},
                'direction': {'enum': ['min', 'max', 'none']}, 'role': {'enum': ['loss', 'score', 'other']}}}},
        'view': {'type': 'object', 'required': ['charts', 'numbers', 'primary_metric'], 'properties': {
            'charts': {'type': 'array', 'minItems': 1, 'maxItems': 4, 'uniqueItems': True, 'items': {'type': 'string'}},
            'numbers': {'type': 'array', 'maxItems': 4, 'uniqueItems': True, 'items': {'type': 'string'}},
            'primary_metric': {'type': 'string'}}}
    }
}


def validate(meta):
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(meta)
    if meta['variant']['kind'] != 'baseline' and not meta['variant'].get('description', '').strip():
        raise ValueError('非基线方案必须填写改动说明')
    if any(k not in meta['metrics'] for k in meta['view']['charts'] + meta['view']['numbers'] + [meta['view']['primary_metric']]):
        raise ValueError('视图引用了未定义的指标')
    return meta


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('时间必须包含时区')
    return dt.timestamp()
