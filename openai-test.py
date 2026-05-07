from ai_auditor import AIAuditor

def test_openai_integration():
    print("🚀 开始 OpenAI 审计功能测试...")
    
    # 1. 实例化审计员
    auditor = AIAuditor()
    
    # 2. 模拟一个高风险的期权交易数据
    # 假设：标的暴涨后 RSI 极高，我们却要 Buy Call
    test_data = {
        "symbol": "TSLA",
        "strategy": "LONG CALL",
        "underlying_price": 250.45,
        "strike": "255C",
        "expiry": "7DTE",
        "market": "BULL",
        "rsi": 82.5,     # 超买严重
        "vol_ratio": 0.8 # 成交量萎缩
    }
    
    print(f"\n📝 测试数据: {test_data['symbol']} {test_data['strategy']} (RSI: {test_data['rsi']})")
    print("-" * 30)

    # 3. 执行审计
    try:
        # 调用 OpenAI 引擎
        result = auditor.audit(engine='openai', mode='options', data=test_data)
        
        print(f"🤖 OpenAI 审计结果:\n{result}")
        
        # 简单校验结果是否包含预期的标签格式
        if "[" in result and "]" in result:
            print("\n✅ 测试通过：OpenAI 返回了正确的格式化审计建议。")
        else:
            print("\n⚠️ 格式警报：OpenAI 返回了内容，但可能未严格遵守标签格式。")
            
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")

if __name__ == "__main__":
    test_openai_integration()