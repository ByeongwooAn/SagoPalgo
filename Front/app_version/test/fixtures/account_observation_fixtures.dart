const beforeObservationId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const afterObservationId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const observationApiNames = ['SSQM1801', 'SSQM2932', 'SSQM2952', 'SSQM2341'];

Map<String, dynamic> observationDetailJson(
  String id, {
  String state = 'COMPLETED',
  int minute = 0,
  String quantity = '0.123456',
}) => {
  'requestId': id,
  'orderDate': '20261102',
  'storageState': state,
  'readOnly': true,
  'createdAt': DateTime.utc(2026, 11, 2, 1, minute).toIso8601String(),
  if (state == 'FAILED') 'failureCode': 'OBSERVATION_FAILED',
  if (state != 'PENDING')
    'completedAt': DateTime.utc(2026, 11, 2, 1, minute, 1).toIso8601String(),
  if (state == 'COMPLETED') ...{
    'observationId': id,
    'snapshotStatus': 'SUCCESS',
    'observation': {
      'contractVersion': 'KB_ACCOUNT_OBSERVATION_V1',
      'observationId': id,
      'provider': 'KB',
      'accountAlias': 'primary',
      'startedAt': DateTime.utc(2026, 11, 2, 1, minute).toIso8601String(),
      'completedAt': DateTime.utc(2026, 11, 2, 1, minute, 1).toIso8601String(),
      'status': 'SUCCESS',
      'atomic': false,
      'usableForTrading': false,
      'sections': [
        for (var i = 0; i < 4; i++)
          {
            'api': observationApiNames[i],
            'scope': i == 3
                ? {'orderDate': '20261102', 'executionClassification': '0'}
                : {'basis': observationApiNames[i]},
            'status': 'SUCCESS',
            'completeness': 'COMPLETE',
            'startedAt': DateTime.utc(2026, 11, 2, 1, minute).toIso8601String(),
            'completedAt': DateTime.utc(
              2026,
              11,
              2,
              1,
              minute,
              1,
            ).toIso8601String(),
            'pagesRead': 1,
            'receivedRowCount': i == 2 ? 1 : 0,
            'reportedTotalCount': i == 2 ? 1 : 0,
            'summary': i == 1
                ? {'ordr_psbl_csh': null, 'tfnd': '0'}
                : <String, dynamic>{},
            'rows': [
              if (i == 2)
                {
                  'fields': {
                    'is_cd': '005930',
                    'is_nm': '삼성전자',
                    'clsf': 'A',
                    'crncy_cd': 'KRW',
                    'is_dtl_typ_cd': '01',
                    'fnl_ccls_excg_cd': 'KRX',
                    'hld_q_p6': quantity,
                    'now_prc': null,
                  },
                },
            ],
            'issues': <dynamic>[],
          },
      ],
    },
  },
};

Map<String, dynamic> observationSummaryJson(String id, {int minute = 0}) =>
    observationDetailJson(id, minute: minute)..remove('observation');

Map<String, dynamic> observationComparisonJson({bool blocked = false}) => {
  'contractVersion': 'KB_ACCOUNT_COMPARISON_V1',
  'readOnly': true,
  'usableForTrading': false,
  'before': {'requestId': beforeObservationId},
  'after': {'requestId': afterObservationId},
  'status': blocked ? 'PARTIAL' : 'COMPARED',
  'sections': [
    for (var i = 0; i < 4; i++)
      {
        'api': observationApiNames[i],
        'beforeScope': <String, dynamic>{},
        'afterScope': <String, dynamic>{},
        'status': blocked && i == 0 ? 'BLOCKED' : 'COMPARED',
        'reasons': [if (blocked && i == 0) 'SCOPE_MISMATCH'],
        'summaryChanges': <dynamic>[],
        'rowChanges': [
          if (i == 2)
            {
              'kind': 'CHANGED',
              'identity': {
                'is_cd': '005930',
                'crncy_cd': 'KRW',
                'fnl_ccls_excg_cd': 'KRX',
              },
              'fields': [
                {
                  'field': 'hld_q_p6',
                  'beforePresent': true,
                  'afterPresent': true,
                  'beforeValue': '0.123456',
                  'afterValue': '0.123457',
                  'numericDelta': '0.000001',
                },
                {
                  'field': 'now_prc',
                  'beforePresent': false,
                  'afterPresent': true,
                  'beforeValue': null,
                  'afterValue': null,
                  'numericDelta': null,
                },
              ],
            },
        ],
      },
  ],
};
