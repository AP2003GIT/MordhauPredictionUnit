import React, { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { RefreshCw, Database, Activity, Trophy } from "lucide-react";
import { fetchPrediction, fetchRatings, ingestHistory } from "./api";
import "./styles.css";

function App() {
  const [prediction, setPrediction] = useState(null);
  const [ratings, setRatings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [predictionData, ratingsData] = await Promise.all([
        fetchPrediction(),
        fetchRatings(20),
      ]);
      setPrediction(predictionData);
      setRatings(ratingsData.players || []);
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
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

      <section className="leaderboard">
        <div className="section-heading">
          <h2>Top player ratings</h2>
          <span>{ratings.length} loaded</span>
        </div>
        <div className="rating-table">
          {ratings.map((player, index) => (
            <div className="rating-row" key={player.fabid}>
              <span className="rank">{index + 1}</span>
              <span className="player-name">{player.name}</span>
              <span>{player.displayRating}</span>
              <span>{player.matches} matches</span>
              <span>{player.kd} KD</span>
            </div>
          ))}
        </div>
      </section>
    </main>
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

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
