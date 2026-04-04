import { useState } from 'react';
import { useSessionStore } from './store/sessionStore';
import SessionStart from './pages/SessionStart';
import Reading from './pages/Reading';

type AppScreen = 'start' | 'reading';

export default function App() {
  const [screen, setScreen] = useState<AppScreen>('start');
  const { sessionId } = useSessionStore();

  function handleSessionStarted() {
    setScreen('reading');
  }

  return (
    <div className="flex flex-col min-h-screen bg-zinc-950 text-zinc-100">
      {screen === 'start' || !sessionId ? (
        <SessionStart onStarted={handleSessionStarted} />
      ) : (
        <Reading />
      )}
    </div>
  );
}
