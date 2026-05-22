import sys
import random
import yaml
import argparse
import itertools
import re

def parse_arguments():
    parser = argparse.ArgumentParser(description="Role Assigner CLI")
    parser.add_argument('--issue_file', type=str, required=True, help='Path to raw issue body file')
    return parser.parse_args()

def parse_github_issue(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    mode = "fairness_first"
    if "satisfaction_first" in content and "fairness_first" not in content.split("satisfaction_first"):
        if content.find("satisfaction_first") < content.find("fairness_first") or content.find("fairness_first") == -1:
            mode = "satisfaction_first"

    sections = re.split(r'### \d+\.', content)
    
    roles_raw = ""
    prefs_raw = ""
    
    for section in sections:
        if "各役職の定員" in section:
            roles_raw = section.split("各役職の定員")[-1].strip()
        elif "メンバーの希望順位" in section:
            prefs_raw = section.split("メンバーの希望順位")[-1].strip()

    # --- エラーハンドリング1: 入力フォーマット（YAML形式）のチェック ---
    try:
        roles = yaml.safe_load(roles_raw) if roles_raw else {}
        if roles is None: roles = {}
    except yaml.YAMLError as e:
        print("### ❌ エラー: 【2. 各役職の定員】の入力形式が正しくありません")
        print("以下を確認して、もう一度新しいIssueからやり直してください。")
        print("- 全角のコロン（`：`）や全角スペースが混ざっていませんか？")
        print("- 項目ごとに正しく改行されていますか？")
        print(f"\n> 詳しいエラー内容: `{e}`")
        sys.exit(1)

    try:
        preferences = yaml.safe_load(prefs_raw) if prefs_raw else {}
        if preferences is None: preferences = {}
    except yaml.YAMLError as e:
        print("### ❌ エラー: 【3. メンバーの希望順位】の入力形式が正しくありません")
        print("以下を確認して、もう一度新しいIssueからやり直してください。")
        print("- 全角のコロン（`：`）、全角スペース、全角カッコ（`｛｝`）が混ざっていませんか？")
        print("- メンバー名や役職名、数値の間に半角コロンと半角スペース ` : ` がありますか？")
        print("- カッコの閉じ忘れはありませんか？")
        print(f"\n> 詳しいエラー内容: `{e}`")
        sys.exit(1)
    
    return mode, roles, preferences

def solve_satisfaction_first(preferences, role_counts):
    assignments = {member: None for member in preferences.keys()}
    remaining_roles = role_counts.copy()
    
    all_ranks = [r for prefs in preferences.values() if prefs for r in prefs.values()]
    max_rank = max(all_ranks) if all_ranks else 1

    for rank in range(1, max_rank + 1):
        role_demands = {role: [] for role in role_counts.keys()}
        for member, prefs in preferences.items():
            if assignments[member] is not None:
                continue
            desired_roles = [role for role, r in prefs.items() if r == rank]
            for role in desired_roles:
                if role in role_demands:
                    role_demands[role].append(member)

        active_roles = [r for r, count in remaining_roles.items() if count > 0 and len(role_demands[r]) > 0]
        sorted_roles = sorted(
            active_roles,
            key=lambda r: len(role_demands[r]) / remaining_roles[r],
            reverse=True
        )

        for role in sorted_roles:
            candidates = role_demands[role]
            valid_candidates = [c for c in candidates if assignments[c] is None]
            if not valid_candidates:
                continue
            
            random.shuffle(valid_candidates)
            available_slots = remaining_roles[role]
            chosen_members = valid_candidates[:available_slots]

            for member in chosen_members:
                assignments[member] = (role, rank, False)
                remaining_roles[role] -= 1

    _assign_unfilled(assignments, remaining_roles)
    return assignments

def solve_fairness_first(preferences, role_counts):
    members = list(preferences.keys())
    flat_roles = []
    for role, count in role_counts.items():
        flat_roles.extend([role] * count)
        
    best_patterns = []
    min_max_penalty = float('inf')
    min_total_penalty = float('inf')

    seen_combinations = set()
    for p in itertools.permutations(flat_roles):
        if p in seen_combinations:
            continue
        seen_combinations.add(p)
        
        current_max_penalty = 0
        current_total_penalty = 0
        current_pattern = {}

        for member, role in zip(members, p):
            rank = preferences[member].get(role, 99)
            current_pattern[member] = (role, rank, rank == 99)
            
            penalty = rank ** 4 if rank != 99 else 10000
            current_total_penalty += penalty
            if penalty > current_max_penalty:
                current_max_penalty = penalty

        if current_max_penalty < min_max_penalty:
            min_max_penalty = current_max_penalty
            min_total_penalty = current_total_penalty
            best_patterns = [current_pattern]
        elif current_max_penalty == min_max_penalty:
            if current_total_penalty < min_total_penalty:
                min_total_penalty = current_total_penalty
                best_patterns = [current_pattern]
            elif current_total_penalty == min_total_penalty:
                best_patterns.append(current_pattern)

    return random.choice(best_patterns)

def _assign_unfilled(assignments, remaining_roles):
    unassigned_members = [m for m, r in assignments.items() if r is None]
    unfilled_roles = [r for r, count in remaining_roles.items() if count > 0]
    for member in unassigned_members:
        if unfilled_roles:
            spare_role = unfilled_roles
            assignments[member] = (spare_role, None, True)
            remaining_roles[spare_role] -= 1
            if remaining_roles[spare_role] == 0:
                unfilled_roles.pop(0)

def main():
    args = parse_arguments()
    mode, roles, preferences = parse_github_issue(args.issue_file)

    # --- エラーハンドリング2: 未入力のチェック ---
    if not roles or not preferences:
        print("### ❌ エラー: データの読み込みに失敗しました")
        print("入力フォームが空欄になっているか、形式が間違っています。")
        print("最初から表示されている初期サンプルデータの書き方を参考に、もう一度新しくIssueを作成し直してください。")
        sys.exit(1)

    total_slots = sum(roles.values())
    total_people = len(preferences)

    # --- エラーハンドリング3: 人数と定員の不一致チェック（ワースト回避モード時のみ必須） ---
    if mode == "fairness_first" and total_slots != total_people:
        print("### ❌ エラー: 総定員数とメンバーの人数が一致していません")
        print(f"現在、**総定員数は {total_slots}人**、**メンバー数は {total_people}人** として入力されています。")
        print("\n【ワースト回避モード】を正確に実行するには、全員にいずれかの役職を過不足なく割り当てる必要があるため、**総定員数と人数を完全に一致させる必要があります。**")
        print("以下、いずれかの方法で修正し、もう一度新しくIssueを作成し直してください。")
        print("1. 役職の定員の数値を調整して、合計人数と合わせる")
        print("2. メンバーの行を追加・削除して、総定員数と合わせる")
        print("3. または、人数がズレていても動作する **【第1希望最優先モード（satisfaction_first）】** を選んで実行する")
        sys.exit(1)

    if mode == "fairness_first":
        results = solve_fairness_first(preferences, roles)
    else:
        if total_slots != total_people:
            print("### ⚠️ 【確認】メンバー数と総定員数が一致していません。")
            print(f"入力された人数: {total_people}人 / 総定員数: {total_slots}人")
            print("『第1希望最優先モード』として、可能な範囲で自動割り振りと希望外分配を実行します。\n")
        results = solve_satisfaction_first(preferences, roles)

    print(f"### 📊 役職割り当て結果 ({'ワースト回避モード' if mode == 'fairness_first' else '第1希望最優先モード'})\n")
    print("| 名前 | 割り当て役職 |")
    print("| :--- | :--- |")
    for name, (role, rank, is_out_of_bounds) in results.items():
        if is_out_of_bounds:
            display_role = f"**{role}** (希望外分配)"
        else:
            display_role = f"**{role}** ({rank}希望)"
        print(f"| {name} | {display_role} |")

if __name__ == "__main__":
    main()
