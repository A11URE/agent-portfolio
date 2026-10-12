<template>
  <div class="fund-advisor">
    <div class="fa-header">
      <div class="fa-title">简投·智顾</div>
      <div class="fa-subtitle">AI 驱动的 ETF 基金投资助手</div>
    </div>

    <a-tabs v-model="activeTab" size="large" @change="onTabChange">
      <!-- ===== Tab 1: 总览 ===== -->
      <a-tab-pane key="dashboard" tab="总览">
        <a-spin :spinning="dashLoading">
          <a-row :gutter="16">
            <a-col :span="6"><a-card :bordered="false" class="fa-stat-card" size="small">
              <div style="font-size:40px;font-weight:700;" :style="{color:dashSent.avg_change>0?'#ef4444':'#10b981'}">{{ dashSent.avg_change>0?'+':'' }}{{ dashSent.avg_change }}%</div>
              <div style="color:rgba(0,0,0,.45);">平均涨跌 ({{ dashSent.total }}只)</div>
            </a-card></a-col>
            <a-col :span="6"><a-card :bordered="false" class="fa-stat-card" size="small">
              <div style="font-size:40px;font-weight:700;color:#ef4444;">{{ dashSent.up }}</div>
              <div style="color:rgba(0,0,0,.45);">上涨</div>
            </a-card></a-col>
            <a-col :span="6"><a-card :bordered="false" class="fa-stat-card" size="small">
              <div style="font-size:40px;font-weight:700;color:#10b981;">{{ dashSent.down }}</div>
              <div style="color:rgba(0,0,0,.45);">下跌</div>
            </a-card></a-col>
            <a-col :span="6"><a-card :bordered="false" class="fa-stat-card" size="small">
              <div style="font-size:24px;font-weight:700;">{{ dashSent.avg_change>0.5?'乐观':dashSent.avg_change<-0.5?'悲观':'中性' }}</div>
              <div style="color:rgba(0,0,0,.45);">市场情绪</div>
            </a-card></a-col>
          </a-row>
          <a-row :gutter="16" style="margin-top:16px;">
            <a-col :span="12">
              <a-card title="🔥 领涨" :bordered="false" size="small">
                <a-list :data-source="dashTop" size="small"><a-list-item slot="renderItem" slot-scope="item" style="cursor:pointer" @click="showEtfDetail(item)">
                  <a-tag color="red">{{ (item.change>=0?'+':'')+item.change.toFixed(2)+'%' }}</a-tag>
                  <span style="margin-left:8px;">{{ item.name }}</span>
                  <span style="color:rgba(0,0,0,.35);margin-left:auto;">{{ item.code }}</span>
                </a-list-item></a-list>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card title="❄️ 领跌" :bordered="false" size="small">
                <a-list :data-source="dashBot" size="small"><a-list-item slot="renderItem" slot-scope="item" style="cursor:pointer" @click="showEtfDetail(item)">
                  <a-tag color="green">{{ (item.change>=0?'+':'')+item.change.toFixed(2)+'%' }}</a-tag>
                  <span style="margin-left:8px;">{{ item.name }}</span>
                  <span style="color:rgba(0,0,0,.35);margin-left:auto;">{{ item.code }}</span>
                </a-list-item></a-list>
              </a-card>
            </a-col>
          </a-row>
          <a-row :gutter="16" style="margin-top:16px;" v-if="dashPE.length>0">
            <a-col :span="8" v-for="p in dashPE" :key="p.index"><a-card :bordered="false" size="small" class="fa-stat-card">
              <div style="font-weight:600;">{{ p.index }}</div>
              <div style="font-size:24px;font-weight:700;margin:4px 0;">PE {{ p.pe }}</div>
              <a-tag :color="p.status==='低估'?'green':p.status==='高估'?'red':'default'">{{ p.status }} ({{ p.pct }}%分位)</a-tag>
            </a-card></a-col>
          </a-row>
        </a-spin>
      </a-tab-pane>

      <!-- ===== Tab 2: 智能问答 ===== -->
      <a-tab-pane key="chat" tab="智能问答">
        <a-card :bordered="false">
          <!-- Quick buttons -->
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
            <a-button size="small" @click="askQuestion('今天市场情绪如何？')">市场快报</a-button>
            <a-button size="small" @click="askQuestion('有哪些高股息ETF值得关注？')">高股息</a-button>
            <a-button size="small" @click="askQuestion('现在应该加仓还是减仓？')">仓位建议</a-button>
            <a-button size="small" @click="askQuestion('给我推荐一个30岁进攻型的组合')">组合推荐</a-button>
            <a-button size="small" @click="showBenchmark=true">ETF对标</a-button>
            <a-button size="small" @click="clearChat" style="margin-left:auto;">清空</a-button>
          </div>
          <!-- Chat area -->
          <div class="chat-area" ref="chatArea">
            <div v-if="chatMessages.length===0" class="chat-empty">
              <a-icon type="robot" style="font-size:48px;color:#1890ff;margin-bottom:16px;" />
              <div>点击上方快捷按钮或直接输入问题</div>
            </div>
            <div v-for="(m,i) in chatMessages" :key="i" :class="['chat-msg',m.role]">
              <div class="msg-bubble">
                <template v-if="m.role==='assistant'">
                  <div v-for="(seg,j) in parseMarkdown(m.content)" :key="j">
                    <a-table v-if="seg.type==='table'" :columns="seg.cols" :data-source="seg.rows"
                      :pagination="false" size="small" :row-key="(r,k)=>k" style="margin:8px 0;" />
                    <div v-else style="white-space:pre-wrap;">{{ seg.text }}</div>
                  </div>
                </template>
                <template v-else>{{ m.content }}</template>
              </div>
            </div>
          </div>
          <div class="chat-input-row">
            <a-input-search v-model="chatInput" placeholder="输入基金问题或ETF代码..." enter-button="发送" :loading="chatLoading" @search="askQuestion(chatInput)" size="large" />
          </div>
          <!-- Benchmark Modal -->
          <a-modal :visible="showBenchmark" title="ETF 对标比较" :footer="null" @cancel="showBenchmark=false" width="500px">
            <a-input-search v-model="benchCode" placeholder="输入ETF代码，如 510300" enter-button="查找" :loading="benchLoading" @search="doBenchmark" size="large" style="margin-bottom:16px;" />
            <div v-if="benchTarget">
              <a-descriptions :title="benchTarget.name+' ('+benchTarget.code+')'" size="small" bordered>
                <a-descriptions-item label="价格">{{ benchTarget.price }}</a-descriptions-item>
                <a-descriptions-item label="涨跌">{{ (benchTarget.change_pct>=0?'+':'')+benchTarget.change_pct.toFixed(2) }}%</a-descriptions-item>
              </a-descriptions>
              <a-divider>相似 ETF</a-divider>
              <a-list :data-source="benchSimilar" size="small"><a-list-item slot="renderItem" slot-scope="item">
                <span style="font-weight:600;">{{ item.name }}</span>
                <span style="margin-left:12px;color:rgba(0,0,0,.45);">{{ item.code }}</span>
                <span :style="{color:item.change_pct>=0?'#ef4444':'#10b981',marginLeft:'auto'}">{{ (item.change_pct>=0?'+':'')+item.change_pct.toFixed(2) }}%</span>
              </a-list-item></a-list>
            </div>
          </a-modal>
        </a-card>
      </a-tab-pane>

      <!-- ===== Tab 3: 市场分析 ===== -->
      <a-tab-pane key="market" tab="市场分析">
        <a-spin :spinning="mktLoading">
          <!-- Section 1: 估值分位 -->
          <a-card title="📊 指数估值分位" :bordered="false" size="small" style="margin-bottom:16px;">
            <a-table :columns="valColumns" :data-source="valData" :pagination="false" size="small" :row-key="r=>r.index_code">
              <template #pe_percentile="pct"><a-progress :percent="pct" size="small" :status="pct<30?'success':pct>70?'exception':'active'" /></template>
              <template #status="s"><a-tag :color="s==='低估'?'green':s==='高估'?'red':'blue'">{{ s }}</a-tag></template>
            </a-table>
          </a-card>

          <!-- Section 2: 主题趋势 -->
          <a-card title="🎯 主题趋势评分" :bordered="false" size="small" style="margin-bottom:16px;">
            <a-row :gutter="12">
              <a-col :span="6" v-for="t in themeData" :key="t.name" style="margin-bottom:8px;">
                <a-card :bordered="false" size="small" class="theme-card">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:600;">{{ t.name }}</span>
                    <a-tag :color="t.trend==='强势'?'red':t.trend==='弱势'?'green':'default'">{{ t.trend }}</a-tag>
                  </div>
                  <div style="font-size:20px;font-weight:700;margin:4px 0;" :style="{color:t.score>55?'#ef4444':t.score<45?'#10b981':'#666'}">{{ t.score.toFixed(0) }} 分</div>
                  <div style="font-size:12px;color:rgba(0,0,0,.45);">均涨跌 {{ t.avg_change>=0?'+':'' }}{{ t.avg_change.toFixed(2) }}%</div>
                </a-card>
              </a-col>
            </a-row>
          </a-card>

          <!-- Section 3: 30日趋势 -->
          <a-card title="📈 30日趋势" :bordered="false" size="small" style="margin-bottom:16px;">
            <a-row :gutter="12">
              <a-col :span="4" v-for="t in trendData.slice(0,6)" :key="t.code" style="margin-bottom:8px;">
                <a-card :bordered="false" size="small" class="fa-stat-card">
                  <div style="font-weight:600;font-size:13px;">{{ t.name }}</div>
                  <div :style="{fontSize:'22px',fontWeight:700,color:t.change_30d>=0?'#ef4444':'#10b981'}">{{ t.change_30d>=0?'+':'' }}{{ t.change_30d }}%</div>
                  <div style="font-size:11px;color:rgba(0,0,0,.45);">{{ t.trend }}趋势</div>
                </a-card>
              </a-col>
            </a-row>
          </a-card>

          <!-- Section 4: ETF 行情 -->
          <a-card :bordered="false" size="small" style="margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span style="font-weight:600;">💹 ETF 实时行情</span>
              <a-button size="small" icon="setting" @click="showEtfMgr=true">管理ETF</a-button>
            </div>
            <a-table :columns="quoteColumns" :data-source="sentData.quotes" :pagination="false" size="small" :row-key="r=>r.code" :scroll="{y:300}" :customRow="r=>({on:{click:()=>showEtfDetail(r)},style:{cursor:'pointer'}})" />
          </a-card>

          <!-- Section 5: PE 走势图 -->
          <a-card title="📉 PE 历史走势" :bordered="false" size="small">
            <a-select v-model="peIndex" style="width:200px;margin-bottom:12px;" @change="loadPETrend">
              <a-select-option value="hs300">沪深300</a-select-option>
              <a-select-option value="zz500">中证500</a-select-option>
              <a-select-option value="sz50">上证50</a-select-option>
            </a-select>
            <div ref="peChart" style="height:300px;"></div>
          </a-card>
        </a-spin>
      </a-tab-pane>

      <!-- ===== Tab 4: 策略工具 ===== -->
      <a-tab-pane key="tools" tab="策略工具">
        <!-- 一键配置 -->
        <a-card :bordered="false" style="margin-bottom:16px;">
          <div style="font-size:16px;font-weight:600;margin-bottom:16px;">🎯 一键配置</div>
          <a-row :gutter="24" align="middle">
            <a-col :span="4"><div style="font-size:12px;color:rgba(0,0,0,.45);margin-bottom:4px;">年龄 {{ configAge }}</div><a-slider v-model="configAge" :min="20" :max="80" style="margin:0;" /></a-col>
            <a-col :span="6"><a-radio-group v-model="configRisk" button-style="solid" size="small"><a-radio-button value="进攻型">进攻型</a-radio-button><a-radio-button value="平衡型">平衡型</a-radio-button><a-radio-button value="防守型">防守型</a-radio-button></a-radio-group></a-col>
            <a-col :span="4"><a-button type="primary" size="large" @click="loadStrategy" :loading="stratLoading" block>生成配置</a-button></a-col>
          </a-row>
          <a-divider v-if="stratResult" />
          <a-row :gutter="16" v-if="stratResult">
            <a-col :span="14">
              <a-alert v-if="awData.alert" :message="awData.alert" :type="awData.alert.includes('超标')?'error':awData.alert.includes('偏高')?'warning':'success'" style="margin-bottom:12px;font-size:12px;" show-icon />
              <a-row :gutter="0">
                <a-col :span="6" v-for="a in ['equity','bond','gold','cash']" :key="a" style="text-align:center;">
                  <div style="font-size:28px;font-weight:700;" :style="{color:a==='equity'?'#ef4444':a==='bond'?'#1890ff':a==='gold'?'#fa8c16':'#666'}">{{ stratResult.allocation[a] }}<span style="font-size:14px;">%</span></div>
                  <div style="font-size:12px;color:rgba(0,0,0,.45);margin-top:2px;">{{ {'equity':'股票','bond':'债券','gold':'黄金','cash':'现金'}[a] }}</div>
                </a-col>
              </a-row>
              <a-divider orientation="left" style="font-size:12px;">波动率监控</a-divider>
              <div v-for="p in awData.portfolio" :key="p.code" style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <span style="font-size:13px;width:90px;">{{ p.name }}</span>
                <span style="font-size:11px;color:rgba(0,0,0,.35);width:40px;">{{ p.code }}</span>
                <a-progress :percent="p.vol||0" :show-info="true" size="small" :stroke-color="p.vol>35?'#ef4444':p.vol>28?'#fa8c16':'#10b981'" style="flex:1;margin:0;" :format="v=>v.toFixed(0)+'%'" />
                <span style="font-size:13px;font-weight:600;min-width:30px;text-align:right;">{{ p.pct }}%</span>
              </div>
              <a-divider orientation="left" style="font-size:12px;">ETF 组合</a-divider>
              <div style="display:flex;flex-wrap:wrap;gap:8px;">
                <a-tag v-for="etf in stratResult.portfolio" :key="etf.code" color="blue" style="font-size:13px;padding:4px 12px;">{{ etf.name }} <b>{{ etf.pct }}%</b></a-tag>
              </div>
            </a-col>
            <a-col :span="10">
              <div style="font-size:13px;font-weight:600;margin-bottom:8px;color:rgba(0,0,0,.45);">📊 策略对比</div>
              <a-spin :spinning="compLoading"><div v-for="s in compScenarios" :key="s.name" style="padding:8px 12px;margin-bottom:6px;background:#fafafa;border-radius:6px;border-left:3px solid #1890ff;">
                <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:500;">{{ s.name }}<span style="color:#ef4444;">{{ s.est_return }}%</span></div>
                <div style="font-size:11px;color:rgba(0,0,0,.35);margin-top:2px;">波动{{ s.est_vol }}% · 回撤{{ s.max_dd }}% · {{ s.desc }}</div>
              </div></a-spin>
              <a-divider style="margin:8px 0;" />
              <div style="font-size:13px;font-weight:600;margin-bottom:8px;color:rgba(0,0,0,.45);">💵 高股息排行</div>
              <a-spin :spinning="divLoading"><div v-for="d in divData.slice(0,5)" :key="d.code" style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                <span>{{ d.name }} <span style="color:rgba(0,0,0,.25);">{{ d.code }}</span></span>
                <span style="color:#52c41a;font-weight:600;">{{ d.div_yield }}%</span>
              </div></a-spin>
            </a-col>
          </a-row>
        </a-card>

        <!-- 定投 + 月度检视 -->
        <a-row :gutter="16">
          <a-col :span="14">
            <a-card :bordered="false" style="margin-bottom:16px;">
              <div style="font-size:16px;font-weight:600;margin-bottom:16px;">💰 定投计算</div>
              <a-row :gutter="16" align="middle">
                <a-col :span="6"><div style="font-size:12px;color:rgba(0,0,0,.45);margin-bottom:4px;">每月投入</div><a-input-number v-model="dcaMonthly" :min="100" :step="1000" size="large" style="width:100%;" /></a-col>
                <a-col :span="6"><div style="font-size:12px;color:rgba(0,0,0,.45);margin-bottom:4px;">投资 {{ dcaYears }} 年</div><a-slider v-model="dcaYears" :min="1" :max="30" /></a-col>
                <a-col :span="6"><div style="font-size:12px;color:rgba(0,0,0,.45);margin-bottom:4px;">年化 {{ dcaReturn }}%</div><a-slider v-model="dcaReturn" :min="1" :max="20" :step="0.5" /></a-col>
                <a-col :span="6"><a-button type="primary" size="large" @click="doDCA" :loading="dcaLoading" block style="margin-top:18px;">计算</a-button></a-col>
              </a-row>
              <a-divider v-if="dcaResult" />
              <a-row :gutter="16" v-if="dcaResult">
                <a-col :span="6" style="text-align:center;"><div style="font-size:12px;color:rgba(0,0,0,.45);">总投入</div><div style="font-size:20px;font-weight:600;">{{ dcaResult.total_invested }}<span style="font-size:12px;">元</span></div></a-col>
                <a-col :span="6" style="text-align:center;"><div style="font-size:12px;color:rgba(0,0,0,.45);">最终价值</div><div style="font-size:20px;font-weight:600;color:#1890ff;">{{ dcaResult.future_value }}<span style="font-size:12px;">元</span></div></a-col>
                <a-col :span="6" style="text-align:center;"><div style="font-size:12px;color:rgba(0,0,0,.45);">总收益</div><div style="font-size:20px;font-weight:600;color:#52c41a;">{{ dcaResult.total_profit }}<span style="font-size:12px;">元</span></div></a-col>
                <a-col :span="6" style="text-align:center;"><div style="font-size:12px;color:rgba(0,0,0,.45);">收益率</div><div style="font-size:20px;font-weight:600;color:#ef4444;">{{ dcaResult.roi }}<span style="font-size:12px;">%</span></div></a-col>
              </a-row>
            </a-card>
          </a-col>
          <a-col :span="10">
            <a-card :bordered="false" style="margin-bottom:16px;">
              <div style="font-size:16px;font-weight:600;margin-bottom:16px;">📋 月度检视</div>
              <div v-for="(p,i) in checkPortfolio" :key="i" style="display:flex;gap:6px;margin-bottom:8px;">
                <a-input v-model="p.name" size="small" style="flex:3;" placeholder="名称" />
                <a-input-number v-model="p.target_pct" size="small" :min="0" :max="100" style="width:60px;" placeholder="目标%" />
                <span style="line-height:24px;color:rgba(0,0,0,.25);">→</span>
                <a-input-number v-model="p.actual_pct" size="small" :min="0" :max="100" style="width:60px;" placeholder="实际%" />
                <a-button size="small" icon="delete" @click="checkPortfolio.splice(i,1)" />
              </div>
              <a-button type="dashed" size="small" @click="checkPortfolio.push({name:'',target_pct:30,actual_pct:28})" style="width:100%;margin-bottom:8px;">+ 添加持仓</a-button>
              <a-button type="primary" size="small" @click="doMonthlyCheck" :loading="checkLoading">开始检视</a-button>
              <span v-if="checkResult" style="margin-left:12px;font-size:12px;" :style="{color:checkResult.needs_rebalance?'#faad14':'#52c41a'}">
                {{ checkResult.needs_rebalance ? '⚠ 偏离'+checkResult.total_drift+'% 需再平衡' : '✅ 无需调整' }}
              </span>
            </a-card>
          </a-col>
        </a-row>
      </a-tab-pane>
    </a-tabs>

    <!-- ETF Detail Modal -->
    <a-modal :visible="!!detailEtf" :title="(detailEtf||{}).name + ' ('+(detailEtf||{}).code+')'" :footer="null" @cancel="detailEtf=null" width="700px">
      <a-descriptions v-if="detailEtf" size="small" bordered :column="2">
        <a-descriptions-item label="价格">{{ detailEtf.price }}</a-descriptions-item>
        <a-descriptions-item label="涨跌">
          <span :style="{color:detailEtf.change_pct>=0?'#ef4444':'#10b981'}">{{ (detailEtf.change_pct>=0?'+':'')+detailEtf.change_pct.toFixed(2) }}%</span>
        </a-descriptions-item>
      </a-descriptions>
      <div ref="klineChart" style="height:300px;margin-top:12px;"></div>
      <div style="margin-top:12px;">
        <a-button type="primary" size="small" @click="openInIDE(detailEtf)">在指标IDE中分析</a-button>
        <a-button size="small" style="margin-left:8px;" @click="addToWatchlist(detailEtf)">加入自选</a-button>
      </div>
    </a-modal>

    <!-- ETF Management Modal -->
    <a-modal :visible="showEtfMgr" title="管理ETF池" :footer="null" @cancel="showEtfMgr=false" width="500px">
      <div style="display:flex;gap:8px;margin-bottom:16px;">
        <a-input v-model="newEtfCode" placeholder="代码(如510300)" size="small" style="width:120px;" />
        <a-input v-model="newEtfName" placeholder="名称" size="small" style="flex:1;" />
        <a-input v-model="newEtfCat" placeholder="类别" size="small" style="width:100px;" />
        <a-button type="primary" size="small" @click="addEtf" :loading="addingEtf">添加</a-button>
      </div>
      <a-list :data-source="sentData.quotes" size="small" :row-key="r=>r.code">
        <a-list-item slot="renderItem" slot-scope="item">
          <span>{{ item.code }} {{ item.name }}</span>
          <a style="color:#ff4d4f;margin-left:auto;" @click="removeEtf(item)">删除</a>
        </a-list-item>
      </a-list>
    </a-modal>
  </div>
</template>

<script>
import { getSentiment, getValuation, getThemes, getTrend30, getDividend, getAllWeather, compareScenarios, calcDCA, getPETrend, getDashboard, fundChat, benchmarkFund, monthlyCheck, getStrategy } from '@/api/fund-advisor'
import * as echarts from 'echarts'

export default {
  name: 'FundAdvisor',
  data () {
    return {
      activeTab: 'dashboard',
      // Dashboard
      dashLoading: false, dashSent: { up:0,down:0,avg_change:0,total:0 }, dashTop: [], dashBot: [], dashPE: [],
      // Chat
      chatInput: '', chatMessages: [], chatLoading: false,
      showBenchmark: false, benchCode: '', benchLoading: false, benchTarget: null, benchSimilar: [],
      // Market
      mktLoading: false,
      valData: [], valColumns: [
        { title:'指数',dataIndex:'index_name',key:'index_name',width:100 },
        { title:'PE',dataIndex:'pe',key:'pe',width:80 },
        { title:'PE分位',dataIndex:'pe_percentile',key:'pe_percentile',scopedSlots:{customRender:'pe_percentile'} },
        { title:'PB',dataIndex:'pb',key:'pb',width:80 },
        { title:'PB分位',dataIndex:'pb_percentile',key:'pb_percentile',width:90 },
        { title:'状态',dataIndex:'status',key:'status',scopedSlots:{customRender:'status'},width:80 },
      ],
      themeData: [],
      trendData: [],
      sentData: { quotes: [], top_movers: [] },
      quoteColumns: [
        { title:'代码',dataIndex:'code',key:'code',width:80, customRender:(v,r)=>({children:v,attrs:{style:'color:#1890ff;cursor:pointer'},on:{click:()=>this.showEtfDetail(r)}}) },
        { title:'名称',dataIndex:'name',key:'name',width:90 },
        { title:'价格',dataIndex:'price',key:'price',width:65, customRender:(v,r)=>this._colorCell(v,r) },
        { title:'涨跌',dataIndex:'change_pct',key:'change_pct',width:65, customRender:v=>({children:(v>=0?'+':'')+v.toFixed(2)+'%',attrs:{style:v>=0?'color:#ef4444':'color:#10b981',fontWeight:600}}) },
        { title:'最高',dataIndex:'high',key:'high',width:65, customRender:(v,r)=>this._colorCell(v,r) },
        { title:'最低',dataIndex:'low',key:'low',width:65, customRender:(v,r)=>this._colorCell(v,r) },
        { title:'成交量(手)',dataIndex:'volume',key:'volume',width:90, customRender:(v,r)=>this._colorVol(v,r) },
        { title:'成交额(万)',dataIndex:'amount',key:'amount',width:90, customRender:(v,r)=>this._colorVol(v,r) },
        { title:'换手率',dataIndex:'turnover',key:'turnover',width:65, customRender:(v,r)=>this._colorTurnover(v,r) },
      ],
      peIndex: 'hs300', peLoading: false, peChart: null,
      peData: { current_pe:0, current_pct:0, min_pe:0, max_pe:0, trend:[] },
      // Tools
      configAge: 35, configRisk: '平衡型', ageMarks: {20:'20',35:'35',50:'50',65:'65',80:'80'}, stratLoading: false, stratResult: null,
      dcaMonthly: 5000, dcaYears: 5, dcaReturn: 8, dcaLoading: false, dcaResult: null,
      awLoading: false, awData: { alert:'', rules:[] },
      awRuleCols: [
        { title:'资产',dataIndex:'asset',key:'asset',width:80,scopedSlots:{customRender:'asset'} },
        { title:'低',dataIndex:'low',key:'low',scopedSlots:{customRender:'low'} },
        { title:'中',dataIndex:'mid',key:'mid',scopedSlots:{customRender:'mid'} },
        { title:'高',dataIndex:'high',key:'high',scopedSlots:{customRender:'high'} },
      ],
      compLoading: false, compScenarios: [],
      divLoading: false, divData: [],
      checkPortfolio: [{name:'沪深300ETF',target_pct:30,actual_pct:28},{name:'中证500ETF',target_pct:30,actual_pct:33},{name:'国债ETF',target_pct:30,actual_pct:29},{name:'黄金ETF',target_pct:10,actual_pct:10}],
      checkLoading: false, checkResult: null,
      detailEtf: null, klineChart: null,
      showEtfMgr: false, newEtfCode: '', newEtfName: '', newEtfCat: '', addingEtf: false,
    }
  },
  mounted () { this.loadDashboard() },
  beforeDestroy () { if (this.peChart) this.peChart.dispose(); if (this.klineChart) this.klineChart.dispose() },
  methods: {
    onTabChange (key) {
      if (key === 'market') { this.loadMarket() }
      else if (key === 'tools') { this.loadTools(); this.refreshAllWeather() }
      else if (key === 'dashboard') { this.loadDashboard() }
    },
    async refreshAllWeather () { this.awLoading=true; const r=await getAllWeather({age:this.configAge,risk:this.configRisk}); if(r.code===1) this.awData=r.data; this.awLoading=false },
    // Dashboard
    async loadDashboard () { this.dashLoading=true; const res=await getDashboard(); if(res.code===1){ const d=res.data; this.dashSent=d.sentiment; this.dashTop=d.top5; this.dashBot=d.bot5; this.dashPE=d.pe_summary }; this.dashLoading=false },
    // Market
    async loadMarket () { this.mktLoading=true; await Promise.all([this.loadValuation(),this.loadThemes(),this.loadTrend30(),this.loadSentiment()]); this.mktLoading=false },
    async loadValuation () { const r=await getValuation(); if(r.code===1) this.valData=r.data },
    async loadThemes () { const r=await getThemes(); if(r.code===1) this.themeData=r.data },
    async loadTrend30 () { const r=await getTrend30(); if(r.code===1) this.trendData=r.data },
    async loadSentiment () { const r=await getSentiment(); if(r.code===1) this.sentData=r.data },
    async loadPETrend () { this.peLoading=true; const r=await getPETrend({index:this.peIndex}); if(r.code===1){ this.peData=r.data; this.$nextTick(()=>this.renderPEChart()) }; this.peLoading=false },
    renderPEChart () {
      if (this.peChart) this.peChart.dispose()
      const dom = this.$refs.peChart; if (!dom||!this.peData.trend.length) return
      this.peChart = echarts.init(dom)
      this.peChart.setOption({
        tooltip:{trigger:'axis'}, grid:{left:55,right:55,top:20,bottom:30},
        xAxis:{type:'category',data:this.peData.trend.map(t=>t.date),axisLabel:{rotate:45,fontSize:10}},
        yAxis:{type:'value',name:'PE'},
        series:[{type:'line',data:this.peData.trend.map(t=>t.pe),smooth:true,lineStyle:{color:'#1890ff',width:2},
          areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(24,144,255,0.3)'},{offset:1,color:'rgba(24,144,255,0.05)'}])},
          markLine:{silent:true,data:[{yAxis:this.peData.min_pe,label:{formatter:'低:'+(this.peData.min_pe||0).toFixed(1)},lineStyle:{color:'#10b981',type:'dashed'}},{yAxis:this.peData.max_pe,label:{formatter:'高:'+(this.peData.max_pe||0).toFixed(1)},lineStyle:{color:'#ef4444',type:'dashed'}}]}}]
      })
    },
    _colorCell (v, r) {
      // Compare with prev_close (昨收): current > prev → red, current < prev → green
      const pc = r ? r.prev_close : null
      const up = pc != null && pc > 0 ? v > pc : (r && r.change_pct >= 0)
      return { children: v ? v.toFixed(3) : '-', attrs: { style: up ? 'color:#ef4444;font-weight:500' : 'color:#10b981;font-weight:500' } }
    },
    _colorVol (v, r) {
      const up = r && r.change_pct != null ? r.change_pct >= 0 : true
      return { children: v ? (v>=10000?(v/10000).toFixed(1)+'万':v.toFixed(0)) : '-', attrs: { style: up ? 'color:#ef4444' : 'color:#10b981' } }
    },
    _colorTurnover (v, r) {
      const up = r && r.change_pct != null ? r.change_pct >= 0 : true
      return { children: v != null ? v.toFixed(2)+'%' : '-', attrs: { style: up ? 'color:#ef4444' : 'color:#10b981' } }
    },
    showEtfDetail (etf) { this.detailEtf={...etf,category:etf.category||(etf.name||'').replace(/[0-9]/g,'').replace('ETF','')}; this.$nextTick(()=>this.renderKline(etf.code)) },
    renderKline (code) {
      if (this.klineChart) this.klineChart.dispose()
      const dom = this.$refs.klineChart; if (!dom) return
      this.$http.get('/api/fund-advisor/kline',{params:{code}}).then(r=>{
        if (r.code!==1||!r.data.length) return
        this.klineChart=echarts.init(dom)
        const dates=r.data.map(d=>d.date); const ohlc=r.data.map(d=>[d.open,d.close,d.low,d.high])
        this.klineChart.setOption({
          tooltip:{trigger:'axis'}, grid:{left:60,right:20,top:10,bottom:30},
          xAxis:{type:'category',data:dates,axisLabel:{rotate:45,fontSize:9}},
          yAxis:{type:'value',scale:true},
          series:[{type:'candlestick',data:ohlc,itemStyle:{color:'#ef4444',color0:'#10b981',borderColor:'#ef4444',borderColor0:'#10b981'}}]
        })
      })
    },
    openInIDE (etf) { window.open('/#/indicator-ide?symbol='+encodeURIComponent(etf.code)+'&market=CNStock') },
    addToWatchlist (etf) { this.$http.post('/api/market/watchlist/add',{market:'CNStock',symbol:etf.code,name:etf.name}).then(()=>this.$message.success(etf.code+' 已加入自选')).catch(()=>this.$message.error('添加失败')) },
    async addEtf () { this.addingEtf=true; await this.$http.post('/api/fund-advisor/etf-pool/add',{code:this.newEtfCode,name:this.newEtfName,category:this.newEtfCat}); this.newEtfCode='';this.newEtfName='';this.newEtfCat=''; this.addingEtf=false; this.loadSentiment();this.$message.success('已添加，重启后端后持久化') },
    async removeEtf (item) { await this.$http.post('/api/fund-advisor/etf-pool/remove',{code:item.code}); this.loadSentiment();this.$message.success('已删除') },
    // Chat
    async askQuestion (q) { if(!q||!q.trim()) return; this.chatMessages.push({role:'user',content:q}); this.chatInput=''; this.chatLoading=true; const res=await fundChat({question:q}); if(res.code===1) this.chatMessages.push({role:'assistant',content:res.data.reply}); else this.chatMessages.push({role:'assistant',content:'抱歉，AI 暂时不可用'}); this.chatLoading=false },
    clearChat () { this.chatMessages=[]; fundChat({question:'',clear:true}).catch(()=>{}) },
    parseMarkdown (text) {
      // Parse Markdown text: split into text segments and table segments
      const segments = []
      const lines = text.split('\n')
      let buf = []
      let tableLines = []
      let inTable = false

      const flushText = () => { if (buf.length) { segments.push({ type: 'text', text: buf.join('\n') }); buf = [] } }
      const flushTable = () => {
        if (tableLines.length >= 2) {
          const header = tableLines[0].split('|').map(s => s.trim()).filter(Boolean)
          const rows = []
          for (let i = 2; i < tableLines.length; i++) {
            const cells = tableLines[i].split('|').map(s => s.trim()).filter(Boolean)
            if (cells.length >= header.length) {
              const row = {}
              header.forEach((h,j) => { row[h] = cells[j] || '' })
              rows.push(row)
            }
          }
          if (header.length > 0 && rows.length > 0) {
            segments.push({ type: 'table', cols: header.map(h => ({ title: h, dataIndex: h, key: h })), rows })
          } else {
            segments.push({ type: 'text', text: tableLines.join('\n') })
          }
        } else {
          buf.push(...tableLines)
        }
        tableLines = []
      }

      for (const line of lines) {
        if (line.startsWith('|')) {
          flushText()
          tableLines.push(line)
          inTable = true
        } else {
          if (inTable) { flushTable(); inTable = false }
          buf.push(line)
        }
      }
      if (inTable) flushTable()
      flushText()
      return segments
    },
    async doBenchmark () { this.benchLoading=true; const r=await benchmarkFund({code:this.benchCode}); if(r.code===1){this.benchTarget=r.data.target;this.benchSimilar=r.data.similar}; this.benchLoading=false },
    // Tools
    async loadTools () { this.compLoading=true; this.divLoading=true; const [cp,div]=await Promise.all([compareScenarios(),getDividend()]); if(cp.code===1) this.compScenarios=cp.data; if(div.code===1) this.divData=div.data; this.compLoading=false; this.divLoading=false; this.refreshAllWeather() },
    applyAllWeather () {
      if (!this.awData.allocation) return
      this.stratResult = {
        allocation: this.awData.allocation,
        portfolio: this.awData.portfolio || [],
        risk: '全天候', age: '-'
      }
      this.$message.success('已应用全天候配置')
    },
    async loadStrategy () { this.stratLoading=true; const r=await getAllWeather({age:this.configAge,risk:this.configRisk}); if(r.code===1) this.stratResult=r.data; this.stratLoading=false },
    async doDCA () { this.dcaLoading=true; const r=await calcDCA({monthly:this.dcaMonthly,years:this.dcaYears,annual_return:this.dcaReturn}); if(r.code===1) this.dcaResult=r.data; this.dcaLoading=false },
    async doMonthlyCheck () { this.checkLoading=true; const r=await monthlyCheck({portfolio:this.checkPortfolio}); if(r.code===1) this.checkResult=r.data; this.checkLoading=false },
  },
}
</script>

<style scoped>
.fund-advisor { padding: 0; }
.fa-header { margin-bottom: 20px; }
.fa-title { font-size: 22px; font-weight: 600; }
.fa-subtitle { font-size: 13px; color: rgba(0,0,0,.45); margin-top: 4px; }
.chat-area { min-height: 350px; max-height: 450px; overflow-y: auto; padding: 16px; background: #fafafa; border-radius: 8px; margin-bottom: 12px; }
.chat-empty { text-align: center; padding: 60px 0; }
.chat-msg { margin-bottom: 12px; display: flex; }
.chat-msg.user { justify-content: flex-end; }
.chat-msg .msg-bubble { max-width: 70%; padding: 10px 16px; border-radius: 12px; line-height: 1.6; white-space: pre-wrap; }
.chat-msg.user .msg-bubble { background: #1890ff; color: #fff; }
.chat-msg.assistant .msg-bubble { background: #fff; border: 1px solid #e8e8e8; }
.fa-stat-card { text-align: center; }
.fa-etf-card { text-align: center; padding: 4px; }
.theme-card { min-height: 100px; }
</style>
