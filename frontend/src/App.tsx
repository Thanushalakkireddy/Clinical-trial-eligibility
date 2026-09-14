import React, { useState } from 'react';
import { Header } from './components/Header';
import { LandingPage, WorkflowTab } from './pages/LandingPage';

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkflowTab>('assessment');

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Header
        onNavigateHome={() => setActiveTab('home')}
        onOpenArchitecture={() => setActiveTab('about')}
      />
      <div className="flex-1">
        <LandingPage activeTab={activeTab} setActiveTab={setActiveTab} />
      </div>
    </div>
  );
}
