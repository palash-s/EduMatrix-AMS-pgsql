import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import { getLeaves } from '../api/ams';
import { useSession } from '../state/session';

export default function LeavesScreen() {
  const { accessToken } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await getLeaves({ token: accessToken });
      setData(res);
    } catch (e) {
      setError(e?.message || 'Failed');
    }
  }

  useEffect(() => {
    load();
  }, []);

  const bal = data?.balance;
  const history = data?.history || [];

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      <View className="bg-mit-purple px-5 pt-14 pb-6">
        <Text className="text-white text-2xl font-extrabold">Leaves</Text>
        <Text className="text-white/80 text-xs mt-1">Balance & history</Text>
        <TouchableOpacity onPress={load} className="mt-4 bg-white/10 px-4 py-2 rounded-xl">
          <Text className="text-white font-bold text-xs">Refresh</Text>
        </TouchableOpacity>
      </View>

      <View className="px-5 -mt-4 pb-10">
        {error ? (
          <View className="bg-red-50 border border-red-100 rounded-2xl p-4 mt-4">
            <Text className="text-red-700 font-bold">{error}</Text>
          </View>
        ) : null}

        <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
          <Text className="text-mit-purple font-extrabold">Balance</Text>
          {bal ? (
            <View className="mt-3">
              <Text className="text-slate-900 font-extrabold text-2xl">{bal.remaining}/{bal.total}</Text>
              <Text className="text-slate-500 text-xs mt-1">Used: {bal.used}</Text>
            </View>
          ) : (
            <Text className="text-slate-500 text-xs mt-3">No balance data</Text>
          )}
        </View>

        <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
          <Text className="text-mit-purple font-extrabold">History</Text>
          {history.length === 0 ? (
            <Text className="text-slate-500 text-xs mt-3">No leave history</Text>
          ) : (
            <View className="mt-3">
              {history.slice(0, 20).map((h) => (
                <View key={String(h.leaveId)} className="py-3 border-b border-slate-100">
                  <View className="flex-row justify-between">
                    <Text className="text-slate-900 font-bold">#{h.leaveId} {h.type}</Text>
                    <Text className="text-slate-700 font-extrabold">{h.status}</Text>
                  </View>
                  <Text className="text-slate-500 text-xs mt-1">
                    {h.startDate} → {h.endDate} · {h.days} days
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
}
