/**
 * k6 Load Test — CTF Cybergames 2026
 * https://2026.ctfcybergames.win
 *
 * Simule 60 joueurs répartis sur les 14 équipes,
 * naviguant sur le site et soumettant des réponses (correctes et incorrectes).
 *
 * Lancement :
 *   k6 run k6_load_test.js
 *
 * Avec rapport HTML (nécessite k6-reporter) :
 *   k6 run --out json=results.json k6_load_test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── URL de base ────────────────────────────────────────────────────────────────
const BASE_URL = 'https://2026.ctfcybergames.win';

// ── Métriques custom ───────────────────────────────────────────────────────────
const submitDuration  = new Trend('submit_duration_ms');
const correctSubmits  = new Counter('correct_submits');
const wrongSubmits    = new Counter('wrong_submits');
const pageLoadOk      = new Rate('page_load_ok');
const submitOk        = new Rate('submit_ok');

// ── Configuration du test ──────────────────────────────────────────────────────
export const options = {
  scenarios: {
    players: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 60 },  // montée en charge
        { duration: '2m',  target: 60 },  // charge soutenue
        { duration: '30s', target: 0  },  // descente
      ],
    },
  },
  thresholds: {
    // 95 % des requêtes sous 3 secondes
    http_req_duration:   ['p(95)<3000'],
    // Taux de succès des chargements de pages > 99 %
    page_load_ok:        ['rate>0.99'],
    // Taux de succès des soumissions (réponse HTTP 200 ou 302) > 95 %
    submit_ok:           ['rate>0.95'],
  },
};

// ── Challenges soumettables (IDs issus de la DB, avec réponses correctes) ─────
//
//  id | slug                  | points
//   1 | extra-stranded-deep   | 3
//   2 | flag-1-imo            | 1
//   3 | flag-2-annonce        | 2
//   4 | flag-3-uen            | 3
//   5 | flag-4-certificat     | 2
//   6 | flag-5-faute          | 1
//   7 | flag-6-abandon-1      | 2
//   8 | flag-7-abandon-2      | 2
//  11 | flag-8a-heure         | 1
//  12 | flag-8b-personnes     | 1
//  13 | flag-8c-armes         | 1
//  14 | flag-8d-position      | 2
//  15 | flag-9a-date          | 1
//  16 | flag-9b-pays          | 1
//
const FLAGS = [
  { id: 1,  label: 'Extra — Stranded Deep',        correct: 'Kharg'                      },
  { id: 2,  label: 'Flag 1 — IMO',                 correct: '9255933'                    },
  { id: 3,  label: 'Flag 2 — Annonce',             correct: '20240902'                   },
  { id: 4,  label: 'Flag 3 — UEN',                 correct: 'T19LL1366C'                 },
  { id: 5,  label: 'Flag 4 — Certificat',          correct: 'PR30092'                    },
  { id: 6,  label: 'Flag 5 — Faute ortho',         correct: 'ACEPTED'                    },
  { id: 7,  label: "Flag 6 — Abandon 1",           correct: "bug/cockroaches infestation" },
  { id: 8,  label: 'Flag 7 — Abandon 2',           correct: '20251008'                   },
  { id: 11, label: 'Flag 8A — Heure',              correct: '0535UTC'                    },
  { id: 12, label: 'Flag 8B — Personnes',          correct: '6'                          },
  { id: 13, label: 'Flag 8C — Armés',              correct: '1'                          },
  { id: 14, label: 'Flag 8D — Position',           correct: '1040017E_011418N'           },
  { id: 15, label: 'Flag 9A — Date saisie',        correct: '20260508'                   },
  { id: 16, label: 'Flag 9B — Pays saisie',        correct: 'IRAN'                       },
];

// Mauvaises réponses génériques pour simuler des erreurs
const WRONG_ANSWERS = ['wronganswer', '000000', 'test123', 'nope', 'XXXXXXX'];

// ── Helpers ────────────────────────────────────────────────────────────────────

function pickWrong() {
  return WRONG_ANSWERS[randomIntBetween(0, WRONG_ANSWERS.length - 1)];
}

function pickFlags(n) {
  const shuffled = FLAGS.slice().sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n);
}

function teamId(vuId) {
  // Répartit les 60 VUs sur les 14 équipes
  return (vuId % 14) + 1;
}

// ── Scénario principal ─────────────────────────────────────────────────────────
export default function () {
  const team = teamId(__VU);
  const jar  = http.cookieJar();

  // Paramètres communs : suivre les redirections, envoyer les cookies
  const params = {
    redirects: 5,
    jar,
    tags: { team: `equipe_${team}` },
  };

  // ── 1. Page d'accueil ────────────────────────────────────────────────────────
  group('01_home', () => {
    const res = http.get(`${BASE_URL}/`, params);
    const ok = check(res, {
      'accueil — status 200': (r) => r.status === 200,
      'accueil — titre présent': (r) => r.body.includes('CTF Cybergames 2026'),
    });
    pageLoadOk.add(ok);
    sleep(randomIntBetween(1, 2));
  });

  // ── 2. Sélection d'équipe ────────────────────────────────────────────────────
  group('02_join_team', () => {
    const res = http.post(
      `${BASE_URL}/teams/${team}/join`,
      {},
      { ...params, tags: { team: `equipe_${team}`, step: 'join' } }
    );
    const ok = check(res, {
      'join team — succès': (r) => r.status === 200 || r.status === 302,
    });
    pageLoadOk.add(ok);
    sleep(randomIntBetween(1, 2));
  });

  // ── 3. Chargement des challenges ─────────────────────────────────────────────
  group('03_view_challenges', () => {
    const res = http.get(`${BASE_URL}/challenges`, params);
    const ok = check(res, {
      'challenges — status 200': (r) => r.status === 200,
      'challenges — formulaires présents': (r) => r.body.includes('Valider'),
    });
    pageLoadOk.add(ok);
    sleep(randomIntBetween(2, 4));
  });

  // ── 4. Soumissions de flags ──────────────────────────────────────────────────
  // Chaque VU tente entre 4 et 8 flags, dans un ordre aléatoire.
  // Pour chaque flag : 70 % de chance d'envoyer la bonne réponse,
  //                    30 % d'envoyer une mauvaise (pour tester le compteur).
  group('04_submit_flags', () => {
    const selected = pickFlags(randomIntBetween(4, 8));

    for (const flag of selected) {
      const sendCorrect = Math.random() < 0.70;
      const answer      = sendCorrect ? flag.correct : pickWrong();

      const start = Date.now();
      const res   = http.post(
        `${BASE_URL}/challenges/${flag.id}/submit`,
        { answer },
        {
          ...params,
          tags: { flag: `flag_${flag.id}`, step: 'submit' },
        }
      );
      submitDuration.add(Date.now() - start);

      const ok = check(res, {
        [`submit ${flag.label} — HTTP ok`]: (r) =>
          r.status === 200 || r.status === 302,
      });
      submitOk.add(ok);

      if (sendCorrect) {
        correctSubmits.add(1);
      } else {
        wrongSubmits.add(1);
      }

      // Pause réaliste entre deux soumissions (lecture de l'énoncé)
      sleep(randomIntBetween(3, 8));
    }
  });

  // ── 5. Consultation du scoreboard ───────────────────────────────────────────
  group('05_scoreboard', () => {
    const res = http.get(`${BASE_URL}/scoreboard`, params);
    const ok  = check(res, {
      'scoreboard — status 200': (r) => r.status === 200,
      'scoreboard — tableau présent': (r) => r.body.includes('Equipe'),
    });
    pageLoadOk.add(ok);
    sleep(randomIntBetween(1, 3));
  });
}

// ── Résumé affiché en fin de test ──────────────────────────────────────────────
export function handleSummary(data) {
  const dur   = data.metrics.http_req_duration;
  const total = data.metrics.http_reqs?.values?.count ?? 0;
  const ok    = data.metrics.page_load_ok?.values?.rate ?? 0;
  const corr  = data.metrics.correct_submits?.values?.count ?? 0;
  const wrong = data.metrics.wrong_submits?.values?.count ?? 0;

  const lines = [
    '═══════════════════════════════════════════',
    '  CTF Cybergames 2026 — Résultats k6',
    '═══════════════════════════════════════════',
    `  Requêtes totales     : ${total}`,
    `  Pages OK (rate)      : ${(ok * 100).toFixed(1)} %`,
    `  Soumissions correctes: ${corr}`,
    `  Soumissions erronées : ${wrong}`,
    `  Latence p50          : ${dur?.values?.['p(50)']?.toFixed(0) ?? '?'} ms`,
    `  Latence p95          : ${dur?.values?.['p(95)']?.toFixed(0) ?? '?'} ms`,
    `  Latence p99          : ${dur?.values?.['p(99)']?.toFixed(0) ?? '?'} ms`,
    '═══════════════════════════════════════════',
  ];

  console.log(lines.join('\n'));

  return {
    stdout: lines.join('\n') + '\n',
  };
}
