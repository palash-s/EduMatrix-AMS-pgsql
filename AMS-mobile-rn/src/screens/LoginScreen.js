import React, { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';

import { login } from '../api/ams';
import { STUDENT_EMAIL_DOMAIN } from '../constants/brand';
import { useSession } from '../state/session';

function normalizeUsername(input) {
  const raw = (input || '').trim();
  if (!raw) return '';
  return raw.includes('@') ? raw : `${raw}${STUDENT_EMAIL_DOMAIN}`;
}

export default function LoginScreen() {
  const { setSession } = useSession();

  const [admissionOrEmail, setAdmissionOrEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const resolvedUsername = useMemo(
    () => normalizeUsername(admissionOrEmail),
    [admissionOrEmail]
  );

  async function onSubmit() {
    setError('');
    setLoading(true);
    try {
      // Keep a stable per-install device id later if needed; backend accepts device_id.
      const deviceId = 'expo';
      const res = await login({
        username: resolvedUsername,
        password,
        deviceId,
      });

      await setSession({
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        user: res.user,
      });
    } catch (e) {
      setError(e?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <View className="flex-1 bg-mit-slateBg">
      {/* Brand header gradient (matches web vibe) */}
      <View className="h-44 bg-mit-purple">
        <View className="flex-1 px-6 pt-14">
          <Text className="text-white text-3xl font-extrabold">AMS</Text>
          <Text className="text-white/90 text-base font-semibold mt-1">Student Portal</Text>
          <Text className="text-white/80 text-xs mt-3">MIT University</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        className="flex-1 px-5 -mt-10"
      >
        <View className="bg-white rounded-2xl p-5 border border-slate-200">
          <Text className="text-slate-800 font-bold text-lg">Login</Text>
          <Text className="text-slate-500 text-xs mt-1">
            Use Admission No or full email
          </Text>

          <View className="mt-4">
            <Text className="text-slate-600 text-xs font-bold mb-2">Admission No / Email</Text>
            <TextInput
              value={admissionOrEmail}
              onChangeText={setAdmissionOrEmail}
              autoCapitalize="none"
              placeholder="e.g. 12345"
              className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-slate-900"
            />
            {admissionOrEmail.trim() && !admissionOrEmail.includes('@') ? (
              <Text className="text-slate-500 text-[11px] mt-2">
                Will use: {resolvedUsername}
              </Text>
            ) : null}
          </View>

          <View className="mt-4">
            <Text className="text-slate-600 text-xs font-bold mb-2">Password</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="Student@123"
              className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-slate-900"
            />
            <Text className="text-slate-500 text-[11px] mt-2">
              Default password (if unchanged): Student@123
            </Text>
          </View>

          {error ? (
            <Text className="text-red-600 text-xs font-semibold mt-3">{error}</Text>
          ) : null}

          <TouchableOpacity
            disabled={loading || !resolvedUsername || !password}
            onPress={onSubmit}
            className={`mt-5 py-3 rounded-xl ${
              loading || !resolvedUsername || !password ? 'bg-slate-300' : 'bg-mit-purple'
            }`}
          >
            <Text className="text-white text-center font-extrabold">
              {loading ? 'Signing in…' : 'Login'}
            </Text>
          </TouchableOpacity>

          <Text className="text-slate-400 text-[10px] mt-4">
            If you’re on a phone, update API base URL to your PC LAN IP.
          </Text>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}
