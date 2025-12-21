import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const SessionContext = createContext(null);

const STORAGE_KEY = 'ams.session.v1';

export function SessionProvider({ children }) {
  const [status, setStatus] = useState('loading'); // loading | ready
  const [accessToken, setAccessToken] = useState('');
  const [refreshToken, setRefreshToken] = useState('');
  const [user, setUser] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        if (raw) {
          const data = JSON.parse(raw);
          setAccessToken(data.accessToken || '');
          setRefreshToken(data.refreshToken || '');
          setUser(data.user || null);
        }
      } finally {
        setStatus('ready');
      }
    })();
  }, []);

  const persist = useCallback(async (next) => {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);

  const setSession = useCallback(
    async ({ accessToken: at, refreshToken: rt, user: u }) => {
      setAccessToken(at || '');
      setRefreshToken(rt || '');
      setUser(u || null);
      await persist({ accessToken: at || '', refreshToken: rt || '', user: u || null });
    },
    [persist]
  );

  const logout = useCallback(async () => {
    setAccessToken('');
    setRefreshToken('');
    setUser(null);
    await AsyncStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo(
    () => ({
      status,
      accessToken,
      refreshToken,
      user,
      isAuthed: Boolean(accessToken),
      setSession,
      logout,
    }),
    [status, accessToken, refreshToken, user, setSession, logout]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
