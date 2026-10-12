import request from '@/utils/request'

export function getSentiment () {
  return request({ url: '/api/fund-advisor/sentiment', method: 'get' })
}
export function getValuation () {
  return request({ url: '/api/fund-advisor/valuation', method: 'get' })
}
export function getThemes () {
  return request({ url: '/api/fund-advisor/themes', method: 'get' })
}
export function fundChat (data) {
  return request({ url: '/api/fund-advisor/chat', method: 'post', data })
}
export function getTrend30 () {
  return request({ url: '/api/fund-advisor/trend30', method: 'get' })
}
export function getDividend () {
  return request({ url: '/api/fund-advisor/dividend', method: 'get' })
}
export function getAllWeather () {
  return request({ url: '/api/fund-advisor/allweather', method: 'get' })
}
export function getDailyBriefing () {
  return request({ url: '/api/fund-advisor/daily', method: 'get' })
}
export function screenFunds (data) {
  return request({ url: '/api/fund-advisor/screen', method: 'post', data })
}
export function monthlyCheck (data) {
  return request({ url: '/api/fund-advisor/monthly', method: 'post', data })
}
export function getStrategy (data) {
  return request({ url: '/api/fund-advisor/strategy', method: 'post', data })
}
export function benchmarkFund (data) {
  return request({ url: '/api/fund-advisor/benchmark', method: 'post', data })
}
export function getKline (params) {
  return request({ url: '/api/fund-advisor/kline', method: 'get', params })
}
export function compareScenarios () {
  return request({ url: '/api/fund-advisor/compare', method: 'post' })
}
export function calcDCA (data) {
  return request({ url: '/api/fund-advisor/dca', method: 'post', data })
}
export function getPETrend (params) {
  return request({ url: '/api/fund-advisor/pe_trend', method: 'get', params })
}
export function getDashboard () {
  return request({ url: '/api/fund-advisor/dashboard', method: 'get' })
}
