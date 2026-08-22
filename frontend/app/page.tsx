'use client';

import React, { useEffect, useState } from 'react';
import { useProjectStore, Project } from '../store/projectStore';
import { storageService } from '../services/storageService';
import { apiClient } from '../services/apiClient';
import Link from 'next/link';

type LanguageOption = {
  value: string;
  label: string;
};

type SupportedLanguagesResponse = {
  languages: Array<{
    code: string;
    name: string;
    native_name: string;
  }>;
};

const fallbackLanguageOptions: LanguageOption[] = [
  { value: 'ar', label: 'Arabic' },
  { value: 'de', label: 'German' },
  { value: 'el', label: 'Greek' },
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'he', label: 'Hebrew' },
  { value: 'hi', label: 'Hindi' },
  { value: 'id', label: 'Indonesian' },
  { value: 'it', label: 'Italian' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'nl', label: 'Dutch' },
  { value: 'pl', label: 'Polish' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'ru', label: 'Russian' },
  { value: 'sv', label: 'Swedish' },
  { value: 'th', label: 'Thai' },
  { value: 'tr', label: 'Turkish' },
  { value: 'uk', label: 'Ukrainian' },
  { value: 'vi', label: 'Vietnamese' },
  { value: 'zh', label: 'Chinese (Simplified)' },
];

export default function ProjectBrowser() {
  const { projects, setProjects, addProject } = useProjectStore();
  const [newProjectName, setNewProjectName] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('es');
  const [languageOptions, setLanguageOptions] = useState<LanguageOption[]>(fallbackLanguageOptions);

  useEffect(() => {
    // Load local project drafts from IndexedDB
    async function loadDrafts() {
      try {
        const drafts = await storageService.listDrafts();
        const mapped: Project[] = drafts.map((d) => ({
          id: d.projectMetadata.id,
          name: d.projectMetadata.name,
          sourceLanguage: d.projectMetadata.sourceLanguage,
          targetLanguage: d.projectMetadata.targetLanguage,
          status: 'draft',
          createdAt: d.projectMetadata.createdAt,
          updatedAt: d.projectMetadata.updatedAt,
        }));
        setProjects(mapped);
      } catch (err) {
        console.error('Failed to load project drafts:', err);
      }
    }

    async function loadSupportedLanguages() {
      try {
        const response = await apiClient.get<SupportedLanguagesResponse>('/translation/languages');
        const options = response.languages.map((language) => ({
          value: language.code,
          label: language.name,
        }));

        if (options.length === 0) {
          return;
        }

        setLanguageOptions(options);
        setSourceLang((current) => (options.some((option) => option.value === current) ? current : 'en'));
        setTargetLang((current) => {
          if (options.some((option) => option.value === current)) {
            return current;
          }

          return options.some((option) => option.value === 'es') ? 'es' : options[0].value;
        });
      } catch (err) {
        console.error('Failed to load supported languages:', err);
      }
    }

    loadDrafts();
    loadSupportedLanguages();
  }, [setProjects]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    const projectId = Math.random().toString(36).substring(7);
    const newProj: Project = {
      id: projectId,
      name: newProjectName,
      sourceLanguage: sourceLang,
      targetLanguage: targetLang,
      status: 'draft',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    // Save to IndexedDB initial draft file
    await storageService.saveDraft({
      version: '1.2.0',
      projectMetadata: {
        id: projectId,
        name: newProjectName,
        sourceLanguage: sourceLang,
        targetLanguage: targetLang,
        createdAt: newProj.createdAt,
        updatedAt: newProj.updatedAt,
      },
      mediaReferences: {
        videoFilename: 'source_video.mp4',
        durationSeconds: 0,
        originalTranscriptSegments: [],
      },
      translations: [],
    });

    addProject(newProj);
    setNewProjectName('');
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="flex justify-between items-center mb-8 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white">Video Translation Studio</h1>
          <p className="text-slate-400 mt-1">Manage, translate, and dub your video assets</p>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Create Project Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-fit">
          <h2 className="text-lg font-bold text-white mb-4">Create New Project</h2>
          <form onSubmit={handleCreateProject} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Project Name</label>
              <input
                type="text"
                placeholder="e.g. Tutorial Video ES"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Source Lang</label>
                <select
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none"
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                >
                  {languageOptions.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Target Lang</label>
                <select
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none"
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                >
                  {languageOptions.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button
              type="submit"
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded-lg transition"
            >
              Initialize Draft
            </button>
          </form>
        </div>

        {/* Project Browser list */}
        <div className="md:col-span-2 space-y-4">
          <h2 className="text-xl font-bold text-white mb-2">Your Draft Projects</h2>
          {projects.length === 0 ? (
            <div className="border border-dashed border-slate-800 rounded-xl p-12 text-center text-slate-500">
              No active drafts found. Create a project on the left panel to begin.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {projects.map((proj) => (
                <div key={proj.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-white truncate">{proj.name}</h3>
                    <div className="flex gap-2 items-center mt-2">
                      <span className="bg-slate-850 px-2 py-0.5 rounded text-xs text-slate-400 uppercase font-mono">{proj.sourceLanguage} &rarr; {proj.targetLanguage}</span>
                      <span className="bg-indigo-950 text-indigo-400 px-2 py-0.5 rounded text-xs font-semibold uppercase">{proj.status}</span>
                    </div>
                  </div>
                  <div className="mt-6 flex justify-between items-center">
                    <span className="text-xs text-slate-500">Updated: {new Date(proj.updatedAt).toLocaleDateString()}</span>
                    <Link
                      href={`/editor/${proj.id}`}
                      className="bg-slate-800 hover:bg-slate-700 text-white font-semibold py-1.5 px-4 rounded-lg text-sm transition"
                    >
                      Open Editor
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
