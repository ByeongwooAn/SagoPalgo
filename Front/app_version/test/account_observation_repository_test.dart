import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/account_observation.dart';
import 'package:app_version/repositories/account_observation_repository.dart';
import 'package:app_version/repositories/spring_account_observation_repository.dart';
import 'package:app_version/services/observation_request_journal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fixtures/account_observation_fixtures.dart';

http.Response ok(dynamic data) => http.Response(
  jsonEncode({'success': true, 'data': data}),
  200,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  late ObservationRequestJournal journal;
  SpringAccountObservationRepository repository(
    http.Client client, {
    String token = '',
    int user = 1,
    String base = 'http://localhost:8080',
    Duration timeout = const Duration(seconds: 60),
  }) => SpringAccountObservationRepository(
    accessToken: token,
    localUserId: user,
    config: ApiConfig(baseUrl: base),
    client: client,
    journal: journal,
    timeout: timeout,
  );
  setUp(() => journal = MemoryObservationRequestJournal());

  test(
    'capture records UUID/date before POST, preserves decimals and confirms terminal result',
    () async {
      late SpringAccountObservationRepository repo;
      var posts = 0;
      repo = repository(
        MockClient((request) async {
          expect(request.method, 'POST');
          posts++;
          expect(request.url.path, '/api/v1/kb/accounts/primary/observations');
          expect(request.headers.containsKey('Authorization'), isFalse);
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body.keys, unorderedEquals(['requestId', 'orderDate']));
          expect(
            body['requestId'],
            matches(RegExp(r'^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$')),
          );
          expect((await repo.outstanding()).single.toJson(), body);
          return ok(observationDetailJson(body['requestId'] as String));
        }),
      );
      final detail = await repo.capture('20261102');
      expect(
        detail.observation!.sections[2].rows.single['hld_q_p6'],
        '0.123456',
      );
      expect(detail.observation!.sections[2].rows.single['now_prc'], isNull);
      expect(await repo.outstanding(), isEmpty);
      expect(posts, 1);
    },
  );

  test(
    'lost response survives repository recreation and recovery is only GET',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'sagopalgo-observation-',
      );
      addTearDown(() => directory.delete(recursive: true));
      final file = File('${directory.path}/requests.jsonl');
      journal = FileObservationRequestJournal(file);
      final calls = <String>[];
      final first = repository(
        MockClient((request) async {
          calls.add(request.method);
          expect(await file.exists(), isTrue);
          throw http.ClientException('private network details');
        }),
      );
      await expectLater(
        first.capture('20261102'),
        throwsA(isA<ObservationRepositoryException>()),
      );
      journal = FileObservationRequestJournal(file);
      final restarted = repository(
        MockClient((request) async {
          calls.add(request.method);
          return ok(observationDetailJson(request.url.pathSegments.last));
        }),
      );
      final pending = (await restarted.outstanding()).single;
      await restarted.check(pending);
      expect(calls, ['POST', 'GET']);
      expect(await restarted.outstanding(), isEmpty);
      expect(
        await file.readAsString(),
        isNot(contains('private network details')),
      );
      expect(await file.readAsString(), isNot(contains('hld_q_p6')));
    },
  );

  test('PENDING stays recoverable and 404 never falls back to POST', () async {
    var requests = 0;
    final repo = repository(
      MockClient((request) async {
        requests++;
        if (request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          return ok(
            observationDetailJson(
              body['requestId'] as String,
              state: 'PENDING',
            ),
          );
        }
        return http.Response(
          jsonEncode({
            'success': false,
            'error': {
              'code': 'RESOURCE_NOT_FOUND',
              'message': 'private account',
            },
          }),
          404,
        );
      }),
    );
    expect((await repo.capture('20261102')).summary.storageState, 'PENDING');
    final pending = (await repo.outstanding()).single;
    await expectLater(
      repo.check(pending),
      throwsA(
        isA<ObservationRepositoryException>().having(
          (e) => e.code,
          'code',
          'HTTP_404',
        ),
      ),
    );
    expect((await repo.outstanding()).single.requestId, pending.requestId);
    expect(requests, 2);
  });

  test(
    'simultaneous clicks issue only one POST and timeout keeps request',
    () async {
      final response = Completer<http.Response>();
      var posts = 0;
      final repo = repository(
        MockClient((_) {
          posts++;
          return response.future;
        }),
        timeout: const Duration(milliseconds: 25),
      );
      final first = repo.capture('20261102');
      await expectLater(
        repo.capture('20261102'),
        throwsA(
          isA<ObservationRepositoryException>().having(
            (e) => e.code,
            'code',
            'BUSY',
          ),
        ),
      );
      await expectLater(
        first,
        throwsA(
          isA<ObservationRepositoryException>().having(
            (e) => e.code,
            'code',
            'CONNECTION_ERROR',
          ),
        ),
      );
      expect(posts, 1);
      expect(await repo.outstanding(), hasLength(1));
      response.complete(
        ok(observationDetailJson((await repo.outstanding()).single.requestId)),
      );
    },
  );

  test('invalid dates are rejected before disk or network', () async {
    var network = 0;
    final repo = repository(
      MockClient((_) async {
        network++;
        return ok({});
      }),
    );
    for (final value in [
      '20260230',
      '20261301',
      '2026112',
      '00000101',
      'bad',
    ]) {
      await expectLater(
        repo.capture(value),
        throwsA(isA<ObservationRepositoryException>()),
      );
    }
    expect(network, 0);
    expect(await repo.outstanding(), isEmpty);
  });

  test('journal write failure stops POST', () async {
    journal = _FailingJournal();
    var network = 0;
    final repo = repository(
      MockClient((_) async {
        network++;
        return ok({});
      }),
    );
    await expectLater(
      repo.capture('20261102'),
      throwsA(
        isA<ObservationRepositoryException>().having(
          (e) => e.code,
          'code',
          'LOCAL_RECORD_ERROR',
        ),
      ),
    );
    expect(network, 0);
  });

  test('history and comparison use GET paths, cursor and auth', () async {
    final calls = <Uri>[];
    final repo = repository(
      MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.headers['Authorization'], 'Bearer token');
        calls.add(request.url);
        return request.url.path.endsWith('/comparison')
            ? ok(observationComparisonJson())
            : ok({
                'items': [observationSummaryJson(beforeObservationId)],
                'nextBeforeId': 4,
              });
      }),
      token: 'token',
    );
    expect((await repo.history(beforeId: 10)).nextBeforeId, 4);
    final comparison = await repo.compare(
      beforeObservationId,
      afterObservationId,
    );
    expect(
      comparison.sections[2].rowChanges.single.fields.first.numericDelta,
      '0.000001',
    );
    expect(calls.first.queryParameters, {'limit': '20', 'beforeId': '10'});
    expect(calls.last.queryParameters, {
      'beforeRequestId': beforeObservationId,
      'afterRequestId': afterObservationId,
    });
  });

  test('rejects same comparison IDs and bad cursor without HTTP', () async {
    var calls = 0;
    final repo = repository(
      MockClient((_) async {
        calls++;
        return ok({});
      }),
    );
    await expectLater(
      repo.compare(beforeObservationId, beforeObservationId.toUpperCase()),
      throwsA(isA<ObservationRepositoryException>()),
    );
    await expectLater(
      repo.history(beforeId: 0),
      throwsA(isA<ObservationRepositoryException>()),
    );
    expect(calls, 0);
  });

  test('server and user namespaces keep recovery IDs separate', () async {
    final client = MockClient(
      (request) async => ok(
        observationDetailJson(
          (jsonDecode(request.body) as Map)['requestId'] as String,
          state: 'PENDING',
        ),
      ),
    );
    final repo = repository(client);
    await repo.capture('20261102');
    expect(await repository(client, user: 2).outstanding(), isEmpty);
    expect(
      await repository(client, base: 'http://other:8080').outstanding(),
      isEmpty,
    );
    expect(await repo.outstanding(), hasLength(1));
  });

  test(
    'mismatched POST ID or malformed body cannot acknowledge request',
    () async {
      final repo = repository(
        MockClient((_) async => ok(observationDetailJson(afterObservationId))),
      );
      await expectLater(
        repo.capture('20261102'),
        throwsA(
          isA<ObservationRepositoryException>().having(
            (e) => e.code,
            'code',
            'INVALID_RESPONSE',
          ),
        ),
      );
      expect(await repo.outstanding(), hasLength(1));
    },
  );

  test('recovery rejects changed date and retains local request', () async {
    var get = false;
    final repo = repository(
      MockClient((request) async {
        if (request.method == 'POST') {
          return ok(
            observationDetailJson(
              (jsonDecode(request.body) as Map)['requestId'] as String,
              state: 'PENDING',
            ),
          );
        }
        get = true;
        final result = observationDetailJson(
          request.url.pathSegments.last,
          state: 'FAILED',
        );
        result['orderDate'] = '20261103';
        return ok(result);
      }),
    );
    await repo.capture('20261102');
    await expectLater(
      repo.check((await repo.outstanding()).single),
      throwsA(isA<ObservationRepositoryException>()),
    );
    expect(get, isTrue);
    expect(await repo.outstanding(), hasLength(1));
  });

  test(
    'HTTP errors and non JSON responses never expose external body',
    () async {
      for (final response in [
        http.Response('<html>private-secret</html>', 502),
        http.Response(
          jsonEncode({
            'success': false,
            'error': {
              'code': 'OBSERVATION_STORAGE_UNAVAILABLE',
              'message': 'private-secret',
            },
          }),
          503,
        ),
      ]) {
        final repo = repository(MockClient((_) async => response));
        await expectLater(
          repo.detail(beforeObservationId),
          throwsA(
            isA<ObservationRepositoryException>().having(
              (e) => e.message,
              'message',
              isNot(contains('private-secret')),
            ),
          ),
        );
      }
    },
  );

  test(
    'numeric JSON and writable contract are not accepted as observation values',
    () {
      final numeric =
          jsonDecode(jsonEncode(observationDetailJson(beforeObservationId)))
              as Map<String, dynamic>;
      ((numeric['observation'] as Map)['sections']
              as List)[2]['rows'][0]['fields']['hld_q_p6'] =
          0.123456;
      expect(() => ObservationDetail.fromJson(numeric), throwsFormatException);
      final writable = observationDetailJson(beforeObservationId);
      (writable['observation'] as Map)['usableForTrading'] = true;
      expect(() => ObservationDetail.fromJson(writable), throwsFormatException);
    },
  );

  test(
    'comparison preserves absent/null and blocked sections cannot contain changes',
    () {
      final comparison = ObservationComparison.fromJson(
        observationComparisonJson(blocked: true),
      );
      final missing = comparison.sections[2].rowChanges.single.fields.last;
      expect(missing.beforePresent, isFalse);
      expect(missing.afterPresent, isTrue);
      expect(missing.afterValue, isNull);
      final malformed = observationComparisonJson(blocked: true);
      (malformed['sections'] as List)[0]['rowChanges'] =
          (malformed['sections'] as List)[2]['rowChanges'];
      expect(
        () => ObservationComparison.fromJson(malformed),
        throwsFormatException,
      );
    },
  );

  test(
    'file journal replays completion without storing account values',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'sagopalgo-journal-',
      );
      addTearDown(() => directory.delete(recursive: true));
      final file = File('${directory.path}/requests.jsonl');
      final store = FileObservationRequestJournal(file);
      await store.start(
        'server1',
        const ObservationRequest(beforeObservationId, '20261102'),
      );
      await store.start(
        'server2',
        const ObservationRequest(afterObservationId, '20261102'),
      );
      await store.complete('server1', beforeObservationId);
      final reloaded = FileObservationRequestJournal(file);
      expect(await reloaded.load('server1'), isEmpty);
      expect(
        (await reloaded.load('server2')).single.requestId,
        afterObservationId,
      );
    },
  );

  test(
    'corrupt recovery journal blocks new POST rather than silently dropping IDs',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'sagopalgo-corrupt-',
      );
      addTearDown(() => directory.delete(recursive: true));
      final file = File('${directory.path}/requests.jsonl');
      await file.writeAsString('{partial');
      journal = FileObservationRequestJournal(file);
      var calls = 0;
      final repo = repository(
        MockClient((_) async {
          calls++;
          return ok({});
        }),
      );
      await expectLater(
        repo.capture('20261102'),
        throwsA(isA<ObservationRepositoryException>()),
      );
      expect(calls, 0);
    },
  );
}

class _FailingJournal extends MemoryObservationRequestJournal {
  @override
  Future<void> start(String context, ObservationRequest request) async =>
      throw const FileSystemException('private path');
}
