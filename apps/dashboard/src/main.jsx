import React, { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  RefreshCw,
  Database,
  Activity,
  Trophy,
  Search,
  SlidersHorizontal,
  UserRound,
  Shuffle,
  BrainCircuit,
} from "lucide-react";
import {
  fetchModelStatus,
  fetchPrediction,
  fetchRandomPrediction,
  fetchRatings,
  ingestHistory,
  trainModel,
} from "./api";
import "./styles.css";

const SOURCE_FILTERS = [
  { value: "all", label: "All sources" },
  { value: "match-history", label: "Match history" },
  { value: "aggregate-stats", label: "Aggregate stats" },
];

const SORT_OPTIONS = [
  { value: "displayRating", label: "Rating" },
  { value: "matches", label: "Matches" },
  { value: "winRate", label: "Win rate" },
  { value: "kd", label: "KD" },
  { value: "kills", label: "Kills" },
];

function App() {
  const [prediction, setPrediction] = useState(null);
  const [ratings, setRatings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [randomLoading, setRandomLoading] = useState(false);
  const [trainingModel, setTrainingModel] = useState(false);
  const [error, setError] = useState("");
  const [randomPrediction, setRandomPrediction] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [playerQuery, setPlayerQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sortKey, setSortKey] = useState("displayRating");
  const [selectedFabid, setSelectedFabid] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [predictionData, ratingsData, modelStatusData] = await Promise.all([
        fetchPrediction(),
        fetchRatings(),
        fetchModelStatus(),
      ]);
      setPrediction(predictionData);
      setRatings(ratingsData.players || []);
      setModelStatus(modelStatusData);
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRandomPrediction() {
    setRandomLoading(true);
    setError("");
    try {
      const predictionData = await fetchRandomPrediction();
      setRandomPrediction(predictionData);
    } catch (err) {
      setError(err.message || "Random prediction failed");
    } finally {
      setRandomLoading(false);
    }
  }

  async function handleTrainModel() {
    setTrainingModel(true);
    setError("");
    try {
      const status = await trainModel();
      setModelStatus(status);
      await refresh();
    } catch (err) {
      setError(err.message || "Model training failed");
    } finally {
      setTrainingModel(false);
    }
  }

  async function handleIngest() {
    setIngesting(true);
    setError("");
    try {
      await ingestHistory();
      await refresh();
    } catch (err) {
      setError(err.message || "Ingest failed");
    } finally {
      setIngesting(false);
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 30000);
    return () => window.clearInterval(id);
  }, []);

  const leader = useMemo(() => {
    if (!prediction?.teams?.length) return null;
    return [...prediction.teams].sort((a, b) => b.probability - a.probability)[0];
  }, [prediction]);

  const filteredRatings = useMemo(() => {
    const query = playerQuery.trim().toLowerCase();

    return [...ratings]
      .filter((player) => {
        if (sourceFilter === "all") return true;
        return player.ratingSource === sourceFilter;
      })
      .filter((player) => {
        if (!query) return true;
        return [player.name, player.fabid, player.ratingSource].some((value) =>
          String(value || "").toLowerCase().includes(query),
        );
      })
      .sort((a, b) => {
        const valueDelta = getPlayerSortValue(b, sortKey) - getPlayerSortValue(a, sortKey);
        if (valueDelta !== 0) return valueDelta;
        return String(a.name || "").localeCompare(String(b.name || ""));
      });
  }, [ratings, playerQuery, sourceFilter, sortKey]);

  const selectedPlayer = useMemo(() => {
    if (!filteredRatings.length) return null;
    return filteredRatings.find((player) => player.fabid === selectedFabid) || filteredRatings[0];
  }, [filteredRatings, selectedFabid]);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Mordhau Prediction Unit</p>
          <h1>Live win probability</h1>
        </div>
        <div className="actions">
          <button onClick={handleIngest} disabled={ingesting}>
            <Database size={18} />
            {ingesting ? "Ingesting" : "Ingest"}
          </button>
          <button onClick={handleRandomPrediction} disabled={randomLoading}>
            <Shuffle size={18} className={randomLoading ? "spin" : ""} />
            {randomLoading ? "Rolling" : "Random 5v5"}
          </button>
          <button onClick={refresh} disabled={loading}>
            <RefreshCw size={18} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </section>

      {error ? <div className="status error">{error}</div> : null}

      <section className="prediction-band">
        <div className="prediction-summary">
          <div className="metric-icon">
            <Activity size={24} />
          </div>
          <div>
            <p className="label">Predicted leader</p>
            <h2>{leader ? leader.name : "No active match"}</h2>
          </div>
        </div>
        <div className="confidence">
          <span>Confidence</span>
          <strong>{formatPercent(prediction?.confidence || 0)}</strong>
        </div>
      </section>

      <PredictionMeter prediction={prediction} />

      <ModelPanel
        modelStatus={modelStatus}
        training={trainingModel}
        onTrain={handleTrainModel}
        prediction={prediction}
        randomPrediction={randomPrediction}
      />

      <section className="grid-two">
        {(prediction?.teams || []).map((team) => (
          <TeamPanel key={team.team} team={team} />
        ))}
        {!prediction?.teams?.length ? (
          <div className="empty-state">
            <Trophy size={28} />
            <h2>{prediction?.message || "Waiting for prediction service"}</h2>
          </div>
        ) : null}
      </section>

      <RandomMatchPanel
        prediction={randomPrediction}
        loading={randomLoading}
        onGenerate={handleRandomPrediction}
      />

      <section className="leaderboard">
        <div className="section-heading player-browser-heading">
          <div>
            <h2>All player ratings</h2>
            <span>
              {filteredRatings.length} of {ratings.length} players shown
            </span>
          </div>
          <SlidersHorizontal size={22} />
        </div>

        <div className="player-controls">
          <label className="search-box">
            <Search size={18} />
            <input
              value={playerQuery}
              onChange={(event) => setPlayerQuery(event.target.value)}
              placeholder="Search player, source, or FAB ID"
            />
          </label>

          <label className="control-select">
            <span>Source</span>
            <select
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
            >
              {SOURCE_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="control-select">
            <span>Sort</span>
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value)}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="player-browser">
          <div className="rating-table" role="list">
            {filteredRatings.map((player, index) => (
              <button
                className={`rating-row ${
                  player.fabid === selectedPlayer?.fabid ? "is-selected" : ""
                }`}
                key={player.fabid}
                onClick={() => setSelectedFabid(player.fabid)}
                type="button"
                aria-pressed={player.fabid === selectedPlayer?.fabid}
              >
                <span className="rank">{index + 1}</span>
                <span className="player-name-block">
                  <strong className="player-name">{player.name}</strong>
                  <small>{sourceLabel(player.ratingSource)}</small>
                </span>
                <span>{formatNumber(player.displayRating)}</span>
                <span>{formatNumber(player.matches)} matches</span>
                <span>{formatDecimal(player.kd)} KD</span>
              </button>
            ))}
            {!filteredRatings.length ? (
              <div className="empty-list">
                <Search size={22} />
                <strong>No players match that view</strong>
              </div>
            ) : null}
          </div>

          <PlayerDetail player={selectedPlayer} />
        </div>
      </section>
    </main>
  );
}

function RandomMatchPanel({ prediction, loading, onGenerate }) {
  const teams = prediction?.teams || [];
  const leader = teams.length
    ? [...teams].sort((a, b) => b.probability - a.probability)[0]
    : null;

  return (
    <section className="simulation-panel">
      <div className="section-heading">
        <div>
          <p className="label">Random 5v5 scrim</p>
          <h2>{leader ? `${leader.name} favored` : "No generated match yet"}</h2>
        </div>
        <button onClick={onGenerate} disabled={loading}>
          <Shuffle size={18} className={loading ? "spin" : ""} />
          {loading ? "Rolling" : prediction ? "Reroll" : "Generate"}
        </button>
      </div>

      {prediction ? (
        <>
          <div className="simulation-meta">
            <span>Confidence {formatPercent(prediction.confidence || 0)}</span>
            <span>Rating diff {formatDecimal(prediction.signals?.ratingDiff || 0, 1)}</span>
            <span>{prediction.signals?.predictionInput || "rating-only"}</span>
            {prediction.mlPrediction?.available ? (
              <span>ML {formatMlProbability(prediction.mlPrediction)}</span>
            ) : null}
          </div>
          <InlinePredictionMeter prediction={prediction} />
          <div className="simulation-teams">
            {teams.map((team) => (
              <SimulatedTeam key={team.team} team={team} />
            ))}
          </div>
        </>
      ) : (
        <div className="simulation-empty">
          <Trophy size={28} />
          <strong>Ready for a generated matchup</strong>
        </div>
      )}
    </section>
  );
}

function ModelPanel({ modelStatus, training, onTrain, prediction, randomPrediction }) {
  const trainMetrics = modelStatus?.metrics?.train;
  const testMetrics = modelStatus?.metrics?.test;

  return (
    <section className="model-panel">
      <div className="section-heading">
        <div>
          <p className="label">Machine learning</p>
          <h2>
            {modelStatus?.available
              ? `${formatNumber(modelStatus.trainingExamples)} training matches`
              : "No trained model yet"}
          </h2>
        </div>
        <button onClick={onTrain} disabled={training}>
          <BrainCircuit size={18} className={training ? "spin" : ""} />
          {training ? "Training" : "Train ML"}
        </button>
      </div>

      <div className="model-layout">
        <div className="model-metrics">
          <StatTile label="Train accuracy" value={formatMetric(trainMetrics?.accuracy)} />
          <StatTile label="Test accuracy" value={formatMetric(testMetrics?.accuracy)} />
          <StatTile label="Log loss" value={formatMetric(testMetrics?.logLoss)} />
          <StatTile label="Brier" value={formatMetric(testMetrics?.brier)} />
        </div>

        <div className="model-scores">
          <ModelProbability title="Live match ML" mlPrediction={prediction?.mlPrediction} />
          <ModelProbability title="Random 5v5 ML" mlPrediction={randomPrediction?.mlPrediction} />
        </div>
      </div>

      {modelStatus?.topWeights?.length ? (
        <div className="signal-strip">
          {modelStatus.topWeights.map((signal) => (
            <span key={signal.feature}>
              {featureLabel(signal.feature)} {formatSigned(signal.weight)}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function ModelProbability({ title, mlPrediction }) {
  if (!mlPrediction?.available) {
    return (
      <div className="model-score">
        <span>{title}</span>
        <strong>Not scored</strong>
      </div>
    );
  }

  return (
    <div className="model-score">
      <span>{title}</span>
      <strong>{formatMlProbability(mlPrediction)}</strong>
    </div>
  );
}

function InlinePredictionMeter({ prediction }) {
  const teams = prediction?.teams || [];
  const iron = teams.find((team) => team.team === 0);
  const free = teams.find((team) => team.team === 1);
  const ironPercent = Math.round((iron?.probability || 0.5) * 100);

  return (
    <div className="inline-meter">
      <div className="meter-labels">
        <strong>{iron?.name || "Iron Company"}</strong>
        <strong>{free?.name || "Free Guard"}</strong>
      </div>
      <div className="meter-track">
        <div className="meter-iron" style={{ width: `${ironPercent}%` }} />
        <div className="meter-free" />
      </div>
      <div className="meter-values">
        <span>{formatPercent(iron?.probability || 0)}</span>
        <span>{formatPercent(free?.probability || 0)}</span>
      </div>
    </div>
  );
}

function SimulatedTeam({ team }) {
  return (
    <div className="simulation-team">
      <div className="section-heading">
        <div>
          <p className="label">{formatPercent(team.probability)}</p>
          <h2>{team.name}</h2>
        </div>
        <span className="score-pill">{formatNumber(team.averageRating)}</span>
      </div>
      <div className="simulated-players">
        {team.players.map((player) => (
          <div className="simulated-player" key={player.fabid}>
            <span className="player-name">{player.name}</span>
            <span>{formatNumber(player.rating)}</span>
            <span>{formatNumber(player.historicalMatches)} matches</span>
            <span>{formatDecimal(player.kd)} KD</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PredictionMeter({ prediction }) {
  const teams = prediction?.teams || [];
  const iron = teams.find((team) => team.team === 0);
  const free = teams.find((team) => team.team === 1);
  const ironPercent = Math.round((iron?.probability || 0.5) * 100);

  return (
    <section className="meter-shell">
      <div className="meter-labels">
        <strong>{iron?.name || "Iron Company"}</strong>
        <strong>{free?.name || "Free Guard"}</strong>
      </div>
      <div className="meter-track">
        <div className="meter-iron" style={{ width: `${ironPercent}%` }} />
        <div className="meter-free" />
      </div>
      <div className="meter-values">
        <span>{formatPercent(iron?.probability || 0)}</span>
        <span>{formatPercent(free?.probability || 0)}</span>
      </div>
    </section>
  );
}

function TeamPanel({ team }) {
  return (
    <section className="team-panel">
      <div className="section-heading">
        <div>
          <p className="label">{formatPercent(team.probability)}</p>
          <h2>{team.name}</h2>
        </div>
        <div className="score-pill">{team.currentScore ?? "-"}</div>
      </div>
      <div className="team-stats">
        <span>Avg rating {team.averageRating}</span>
        <span>Impact {team.liveImpact}</span>
      </div>
      <div className="players">
        {team.players.map((player) => (
          <div className="player-row" key={player.fabid || player.name}>
            <div>
              <strong>{player.name}</strong>
              <span>{player.historicalMatches} historical</span>
            </div>
            <div className="combat-line">
              <span>{player.rating}</span>
              <span>{player.kills}/{player.deaths}/{player.assists}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function PlayerDetail({ player }) {
  if (!player) {
    return (
      <aside className="player-detail empty-detail">
        <UserRound size={34} />
        <h2>No player selected</h2>
      </aside>
    );
  }

  return (
    <aside className="player-detail">
      <div className="player-detail-header">
        {player.steamAvatar ? (
          <img src={player.steamAvatar} alt="" />
        ) : (
          <div className="avatar-fallback">
            <UserRound size={28} />
          </div>
        )}
        <div>
          <p className="label">{sourceLabel(player.ratingSource)}</p>
          <h2>{player.name}</h2>
          <span className="fabid">{player.fabid}</span>
        </div>
      </div>

      <div className="hero-stat">
        <span>Unit rating</span>
        <strong>{formatNumber(player.displayRating)}</strong>
      </div>

      <div className="detail-grid">
        <StatTile label="Matches" value={formatNumber(player.matches)} />
        <StatTile label="Wins" value={formatNumber(player.wins)} />
        <StatTile label="Win rate" value={formatPercent(player.winRate || 0)} />
        <StatTile label="KD" value={formatDecimal(player.kd)} />
        <StatTile label="KDA" value={formatDecimal(player.kda)} />
        <StatTile label="Avg ADR" value={formatDecimal(player.avgAdr, 1)} />
      </div>

      <div className="combat-breakdown">
        <h3>Combat totals</h3>
        <div>
          <span>
            Kills <strong>{formatNumber(player.kills)}</strong>
          </span>
          <span>
            Deaths <strong>{formatNumber(player.deaths)}</strong>
          </span>
          <span>
            Assists <strong>{formatNumber(player.assists)}</strong>
          </span>
        </div>
      </div>

      <div className="combat-breakdown muted-breakdown">
        <h3>Aggregate record</h3>
        <div>
          <span>
            Matches <strong>{formatNumber(player.aggregateMatches)}</strong>
          </span>
          <span>
            Kills <strong>{formatNumber(player.aggregateKills)}</strong>
          </span>
          <span>
            Assists <strong>{formatNumber(player.aggregateAssists)}</strong>
          </span>
        </div>
      </div>
    </aside>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="stat-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function getPlayerSortValue(player, key) {
  const fallbackKeys = {
    matches: ["matches", "aggregateMatches"],
    kills: ["kills", "aggregateKills"],
  };
  const keys = fallbackKeys[key] || [key];

  for (const candidate of keys) {
    const value = Number(player[candidate]);
    if (Number.isFinite(value)) return value;
  }
  return Number.NEGATIVE_INFINITY;
}

function sourceLabel(source) {
  if (source === "match-history") return "Match history";
  if (source === "aggregate-stats") return "Aggregate stats";
  return "Unknown source";
}

function formatMlProbability(mlPrediction) {
  const favoredTeam = mlPrediction.favoredTeam === 0 ? "Iron Company" : "Free Guard";
  const probability =
    mlPrediction.favoredTeam === 0
      ? mlPrediction.team0Probability
      : mlPrediction.team1Probability;
  return `${favoredTeam} ${formatPercent(probability || 0)}`;
}

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number < 1 ? number.toFixed(3) : number.toFixed(2);
}

function formatSigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number >= 0 ? "+" : ""}${number.toFixed(3)}`;
}

function featureLabel(feature) {
  const labels = {
    avg_rating_diff: "Avg rating",
    top_rating_diff: "Top player",
    weakest_rating_diff: "Weakest player",
    rating_spread_diff: "Rating spread",
    avg_matches_diff: "Experience",
    total_matches_diff: "Total matches",
    avg_win_rate_diff: "Win rate",
    avg_kd_diff: "KD",
    avg_kda_diff: "KDA",
    avg_adr_diff: "ADR",
    team_size_diff: "Team size",
  };
  return labels[feature] || feature;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return new Intl.NumberFormat().format(number);
}

function formatDecimal(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(number);
}

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
