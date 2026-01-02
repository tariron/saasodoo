import React, { useState, useEffect } from 'react';
import { instanceAPI, Instance } from '../utils/api';

interface Backup {
  backup_id: string;
  backup_name: string;
  instance_name: string;
  created_at: string;
  database_size: number;
  data_size: number;
  total_size: number;
  odoo_version: string;
  status: string;
}

interface BackupsResponse {
  instance_id: string;
  instance_name: string;
  backups: Backup[];
  total_backups: number;
}

interface RestoreModalProps {
  instance: Instance;
  isOpen: boolean;
  onClose: () => void;
  onRestore: (instanceId: string, backupId: string) => Promise<void>;
}

const RestoreModal: React.FC<RestoreModalProps> = ({ instance, isOpen, onClose, onRestore }) => {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState<'select' | 'confirm'>('select');
  const [createBackupFirst, setCreateBackupFirst] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchBackups();
      setStep('select');
      setSelectedBackup(null);
      setError('');
    }
  }, [isOpen, instance.id]);

  const fetchBackups = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await instanceAPI.backups(instance.id);
      const data: BackupsResponse = response.data;
      setBackups(data.backups || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch backups');
      setBackups([]);
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatRelativeTime = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMinutes < 60) {
      return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 30) {
      return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  const handleSelectBackup = (backupId: string) => {
    setSelectedBackup(backupId);
    setStep('confirm');
  };

  const handleConfirmRestore = async () => {
    if (!selectedBackup) return;

    try {
      setRestoring(true);
      setError('');

      if (createBackupFirst) {
        await instanceAPI.action(instance.id, 'backup', {
          name: `pre_restore_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}`
        });
      }

      await onRestore(instance.id, selectedBackup);
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Restore failed');
    } finally {
      setRestoring(false);
    }
  };

  const handleClose = () => {
    if (!restoring) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const selectedBackupData = backups.find(b => b.backup_id === selectedBackup);

  return (
    <div className="fixed inset-0 bg-warm-900/60 backdrop-blur-sm overflow-y-auto h-full w-full z-50 flex items-start justify-center pt-16 px-4">
      <div className="relative w-full max-w-2xl card p-0 animate-fade-in-up shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-warm-200">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-warm-900">
                Restore Instance
              </h3>
              <p className="text-sm text-warm-500">{instance.name}</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={restoring}
            className="p-2 text-warm-400 hover:text-warm-600 hover:bg-warm-100 rounded-lg transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Warning Banner */}
        <div className="mx-5 mt-5 p-4 bg-rose-50 border border-rose-200 rounded-xl">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-rose-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-rose-800">
                Warning: This will replace ALL current data
              </h3>
              <p className="mt-1 text-sm text-rose-700">
                Restoring a backup will permanently replace all current instance data. This action cannot be undone.
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-5">
          {step === 'select' && (
            <>
              {loading ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <svg className="animate-spin h-10 w-10 text-primary-600 mb-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="text-warm-600">Loading backups...</span>
                </div>
              ) : error ? (
                <div className="text-center py-12">
                  <div className="w-14 h-14 bg-rose-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-7 h-7 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <p className="text-rose-600 mb-4">{error}</p>
                  <button onClick={fetchBackups} className="btn-secondary">
                    Retry
                  </button>
                </div>
              ) : backups.length === 0 ? (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-warm-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-8 h-8 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-medium text-warm-900 mb-2">No backups available</h3>
                  <p className="text-warm-500">
                    This instance has no backups to restore from. Create a backup first.
                  </p>
                </div>
              ) : (
                <>
                  <h4 className="text-sm font-medium text-warm-700 mb-3">
                    Select a backup to restore ({backups.length} available)
                  </h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {backups.map((backup) => (
                      <div
                        key={backup.backup_id}
                        onClick={() => handleSelectBackup(backup.backup_id)}
                        className="p-4 border border-warm-200 rounded-xl hover:border-primary-300 hover:bg-primary-50/50 cursor-pointer transition-all group"
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <h5 className="font-medium text-warm-900 group-hover:text-primary-700">{backup.backup_name}</h5>
                            <div className="mt-1.5 space-y-1">
                              <p className="text-sm text-warm-500">
                                {formatRelativeTime(backup.created_at)}
                                <span className="text-warm-300 mx-2">•</span>
                                {new Date(backup.created_at).toLocaleString()}
                              </p>
                              <div className="flex items-center gap-3 text-xs text-warm-500">
                                <span className="inline-flex items-center">
                                  <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                                  </svg>
                                  {formatFileSize(backup.total_size)}
                                </span>
                                <span className="inline-flex items-center">
                                  <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                                  </svg>
                                  Odoo {backup.odoo_version}
                                </span>
                              </div>
                              <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
                                backup.status === 'completed'
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-amber-100 text-amber-700'
                              }`}>
                                {backup.status}
                              </span>
                            </div>
                          </div>
                          <div className="text-warm-300 group-hover:text-primary-500 transition-colors">
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          {step === 'confirm' && selectedBackupData && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-warm-700">
                Confirm Restore
              </h4>

              {/* Selected backup info */}
              <div className="p-4 bg-warm-50 border border-warm-200 rounded-xl">
                <h5 className="text-xs font-medium text-warm-500 uppercase tracking-wide mb-2">Selected Backup</h5>
                <div className="space-y-1.5 text-sm">
                  <p className="text-warm-900"><strong className="font-medium">Name:</strong> {selectedBackupData.backup_name}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Created:</strong> {formatRelativeTime(selectedBackupData.created_at)}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Size:</strong> {formatFileSize(selectedBackupData.total_size)}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Odoo Version:</strong> {selectedBackupData.odoo_version}</p>
                </div>
              </div>

              {/* Current instance info */}
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl">
                <h5 className="text-xs font-medium text-amber-700 uppercase tracking-wide mb-2">Current Instance (will be replaced)</h5>
                <div className="space-y-1.5 text-sm">
                  <p className="text-warm-900"><strong className="font-medium">Instance:</strong> {instance.name}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Status:</strong> {instance.status}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Last Updated:</strong> {formatRelativeTime(instance.updated_at)}</p>
                  <p className="text-warm-600"><strong className="font-medium text-warm-900">Odoo Version:</strong> {instance.odoo_version}</p>
                </div>
              </div>

              {/* Backup option */}
              <label className="flex items-center p-3 bg-warm-50 rounded-xl cursor-pointer hover:bg-warm-100 transition-colors">
                <input
                  type="checkbox"
                  checked={createBackupFirst}
                  onChange={(e) => setCreateBackupFirst(e.target.checked)}
                  className="w-4 h-4 text-primary-600 bg-white border-warm-300 rounded focus:ring-primary-500"
                />
                <span className="ml-3 text-sm text-warm-700">
                  Create backup of current data before restore <span className="text-emerald-600">(recommended)</span>
                </span>
              </label>

              {error && (
                <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-sm">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-5 border-t border-warm-200 bg-warm-50/50 rounded-b-2xl">
          {step === 'select' ? (
            <button onClick={handleClose} disabled={restoring} className="btn-secondary">
              Cancel
            </button>
          ) : (
            <>
              <button
                onClick={() => setStep('select')}
                disabled={restoring}
                className="btn-secondary"
              >
                Back
              </button>
              <button
                onClick={handleConfirmRestore}
                disabled={restoring || !selectedBackup}
                className="btn-primary bg-rose-600 hover:bg-rose-700 focus:ring-rose-500"
              >
                {restoring ? (
                  <span className="flex items-center">
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {createBackupFirst ? 'Creating Backup & Restoring...' : 'Restoring...'}
                  </span>
                ) : (
                  <span className="flex items-center">
                    <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {createBackupFirst ? 'Backup & Restore' : 'Confirm Restore'}
                  </span>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default RestoreModal;
